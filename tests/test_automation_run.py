"""Tes eksekutor otomatisasi dengan client palsu."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from app.services.automation import AutomationApp, AutomationConfig, ScriptStep
from app.services.automation_run import run_automation
from app.services.groups import DeviceRef


class FakeClock:
    def __init__(self) -> None:
        self._value = 0.0
        self._lock = threading.Lock()

    def now(self) -> float:
        with self._lock:
            return self._value

    def sleep(self, seconds: float) -> None:
        with self._lock:
            self._value += max(0.0, seconds)


class FakeClient:
    def __init__(
        self,
        installed: dict[str, list[str]] | None = None,
        adb_fail: set[str] | None = None,
    ) -> None:
        self.calls: list[tuple] = []
        self.installed = installed or {}
        self.adb_fail = adb_fail or set()
        self._lock = threading.Lock()

    def _record(self, *call) -> None:
        with self._lock:
            self.calls.append(call)

    def control(self, index: str, action: str) -> None:
        self._record("control", str(index), action)

    def wait_android_started(self, index: str, timeout: int = 120) -> bool:
        return True

    def wait_stopped(self, index: str, timeout: int = 45) -> bool:
        return True

    def get_info(self, index: str) -> dict:
        return {"is_android_started": True, "is_process_started": False}

    def list_installed_apps(self, index: str) -> list[tuple[str, str]]:
        packages = self.installed.get(
            str(index), sorted({app for values in self.installed.values() for app in values})
        )
        return [(package, package) for package in packages]

    def launch_app(self, index: str, package: str) -> None:
        self._record("launch_app", str(index), package)

    def adb_shell(self, index: str, command: str, timeout: int = 60) -> str:
        if command in self.adb_fail:
            raise RuntimeError("adb gagal")
        self._record("adb_shell", str(index), command)
        return ""

    def get_screen_size(self, index: str) -> tuple[int, int]:
        return 1280, 720


def _targets(count: int) -> list[tuple[str, str, dict]]:
    return [
        (str(index), f"device{index}", {"name": f"device{index}"})
        for index in range(count)
    ]


class RunAutomationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.report_dir = Path(self._tmp.name) / "logs"
        self.clock = FakeClock()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _config(self, app_count: int = 1, **overrides) -> AutomationConfig:
        values = {
            "batch_size": 3,
            "duration_min_sec": 1,
            "duration_max_sec": 1,
            "interaction_enabled": True,
            "scale_coordinates": True,
            "apps": [
                AutomationApp(package=f"com.example.app{index}")
                for index in range(app_count)
            ],
        }
        values.update(overrides)
        return AutomationConfig(**values)

    def _run(self, client, targets, config, missing=None, should_stop=None):
        if not client.installed:
            packages = [app.package for app in config.enabled_apps()]
            client.installed = {
                str(index): list(packages) for index, _name, _device in targets
            }
        return run_automation(
            client,
            "Grup Tes",
            targets,
            missing or [],
            config,
            self.report_dir,
            progress=lambda _payload: None,
            should_stop=should_stop,
            sleep=self.clock.sleep,
            clock=self.clock.now,
        )

    def test_batch_partition_and_report(self) -> None:
        client = FakeClient()
        config = self._config(app_count=1, batch_size=3)
        report = self._run(client, _targets(7), config)

        self.assertEqual(
            [device.batch for device in report.devices],
            [1, 1, 1, 2, 2, 2, 3],
        )
        self.assertEqual(report.counts().get("success"), 7)
        launches = [call for call in client.calls if call[0] == "launch_app"]
        self.assertEqual(len(launches), 7)
        report_file = Path(report.report_path)
        self.assertTrue(report_file.is_file())
        raw = json.loads(report_file.read_text(encoding="utf-8"))
        self.assertEqual(raw["group"], "Grup Tes")
        self.assertEqual(len(raw["devices"]), 7)

    def test_missing_app_shuts_down_without_session(self) -> None:
        client = FakeClient(
            installed={
                "0": ["com.example.app0"],
                "1": [],
            }
        )
        config = self._config(app_count=1, batch_size=2)
        targets = [
            ("0", "device0", {"name": "device0"}),
            ("1", "device1", {"name": "device1"}),
        ]
        report = self._run(client, targets, config)

        by_name = {device.name: device for device in report.devices}
        self.assertEqual(by_name["device0"].status, "success")
        self.assertEqual(by_name["device1"].status, "failed")
        self.assertEqual(
            by_name["device1"].apps_missing, ["com.example.app0"]
        )
        self.assertIn("tidak terpasang", by_name["device1"].message)

        app_launches = [call for call in client.calls if call[0] == "launch_app"]
        self.assertTrue(all(call[1] == "0" for call in app_launches))
        self.assertIn(("control", "1", "shutdown"), client.calls)

    def test_apps_open_in_order_and_scripts_run(self) -> None:
        client = FakeClient()
        config = self._config(
            batch_size=1,
            scale_coordinates=False,
            apps=[
                AutomationApp(
                    package="com.example.first",
                    steps=[
                        ScriptStep(action="tap", x=60, y=400, delay_ms=0),
                        ScriptStep(action="wait", delay_ms=1000),
                    ],
                ),
                AutomationApp(
                    package="com.example.second",
                    steps=[ScriptStep(action="key", key="home", delay_ms=0)],
                ),
            ],
        )
        report = self._run(
            client,
            [("0", "device0", {"name": "device0"})],
            config,
        )

        launches = [
            (call[1], call[2])
            for call in client.calls
            if call[0] == "launch_app"
        ]
        self.assertEqual(
            launches,
            [
                ("0", "com.example.first"),
                ("0", "com.example.second"),
            ],
        )
        adb_calls = [call[2] for call in client.calls if call[0] == "adb_shell"]
        self.assertEqual(adb_calls, ["input tap 60 400", "input keyevent 3"])
        self.assertEqual(report.devices[0].status, "success")
        self.assertEqual(
            report.devices[0].apps_opened,
            ["com.example.first", "com.example.second"],
        )

    def test_stop_during_first_batch_skips_rest(self) -> None:
        client = FakeClient()
        config = self._config(app_count=1, batch_size=3)
        report = self._run(
            client,
            _targets(8),
            config,
            should_stop=lambda: self.clock.now() > 0,
        )

        counts = report.counts()
        self.assertTrue(report.stopped_by_user)
        self.assertEqual(counts.get("stopped"), 3)
        self.assertEqual(counts.get("skipped"), 5)
        for device in report.devices:
            if device.status == "stopped":
                self.assertIn(("control", device.index, "shutdown"), client.calls)

    def test_script_error_is_reported_but_session_continues(self) -> None:
        client = FakeClient(adb_fail={"input tap 10 20"})
        config = self._config(
            batch_size=1,
            scale_coordinates=False,
            apps=[
                AutomationApp(
                    package="com.example.app0",
                    steps=[ScriptStep(action="tap", x=10, y=20)],
                )
            ],
        )
        report = self._run(
            client,
            [("0", "device0", {"name": "device0"})],
            config,
        )
        self.assertEqual(report.devices[0].status, "success")
        self.assertEqual(len(report.devices[0].script_errors), 1)
        self.assertIn("adb gagal", report.devices[0].script_errors[0])

    def test_missing_group_member_is_reported(self) -> None:
        client = FakeClient()
        config = self._config(app_count=1, batch_size=2)
        report = self._run(
            client,
            [("0", "device0", {"name": "device0"})],
            config,
            missing=[DeviceRef("hilang", "9")],
        )
        by_name = {device.name: device for device in report.devices}
        self.assertEqual(by_name["hilang"].status, "skipped")
        self.assertIn("tidak ditemukan", by_name["hilang"].message)


if __name__ == "__main__":
    unittest.main()
