"""Tes perintah peluncuran aplikasi dan preferensi aplikasi."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.mumu import MuMuClient, MuMuError, _extract_apps
from app.services.settings import AppPrefs, SettingsStore


class RecordingClient(MuMuClient):
    def __init__(self) -> None:
        super().__init__(Path("MuMuManager.exe"))
        self.calls: list[tuple] = []
        self.infos: list[dict] = []

    def _run(self, *args: str, timeout: int | None = None) -> dict:
        self.calls.append(args)
        return {}

    def get_info(self, index: str) -> dict:
        if not self.infos:
            return {"is_android_started": True}
        return self.infos.pop(0)


class LaunchAppTests(unittest.TestCase):
    def test_launch_app_builds_manager_command(self) -> None:
        client = RecordingClient()
        client.launch_app("2", "com.whatsapp")
        self.assertEqual(
            client.calls,
            [
                (
                    "control",
                    "-v",
                    "2",
                    "app",
                    "launch",
                    "--package",
                    "com.whatsapp",
                )
            ],
        )

    def test_launch_app_rejects_empty_package(self) -> None:
        client = RecordingClient()
        with self.assertRaises(MuMuError):
            client.launch_app("2", "   ")
        self.assertEqual(client.calls, [])

    @mock.patch("time.sleep", return_value=None)
    def test_wait_android_started(self, _sleep) -> None:
        client = RecordingClient()
        client.infos = [
            {"is_android_started": False},
            {"is_android_started": True},
        ]
        self.assertTrue(client.wait_android_started("1", timeout=10))

    def test_wait_android_started_timeout(self) -> None:
        client = RecordingClient()
        self.assertFalse(client.wait_android_started("1", timeout=0))

    @mock.patch("time.sleep", return_value=None)
    def test_launch_device_and_app_order(self, _sleep) -> None:
        client = RecordingClient()
        client.infos = [
            {"is_android_started": False},
            {"is_android_started": True},
        ]
        client.launch_device_and_app("3", "com.android.chrome", timeout=10)
        self.assertEqual(
            client.calls,
            [
                ("control", "-v", "3", "launch"),
                ("control", "-v", "3", "app", "launch", "--package", "com.android.chrome"),
            ],
        )

    def test_launch_device_and_app_requires_package(self) -> None:
        client = RecordingClient()
        with self.assertRaises(MuMuError):
            client.launch_device_and_app("3", "")
        self.assertEqual(client.calls, [])

    @mock.patch("time.sleep", return_value=None)
    def test_open_app_retries_until_ready(self, _sleep) -> None:
        class FlakyClient(RecordingClient):
            def __init__(self) -> None:
                super().__init__()
                self.failures = 1

            def _run(self, *args: str, timeout: int | None = None) -> dict:
                self.calls.append(args)
                if "launch" in args and self.failures:
                    self.failures -= 1
                    raise MuMuError("belum siap")
                return {}

        client = FlakyClient()
        client.open_app_when_ready("4", "com.whatsapp", timeout=10, attempts=3)
        app_launches = [call for call in client.calls if "launch" in call]
        self.assertEqual(len(app_launches), 2)


class ExtractAppsTests(unittest.TestCase):
    def test_various_shapes(self) -> None:
        data = {
            "apps": [
                {"package": "com.whatsapp", "label": "WhatsApp"},
                {"package_name": "com.android.chrome", "name": "Chrome"},
            ],
            "com.example.game": {"name": "Game"},
        }
        apps = dict(_extract_apps(data))
        self.assertEqual(apps["com.whatsapp"], "WhatsApp")
        self.assertEqual(apps["com.android.chrome"], "Chrome")
        self.assertEqual(apps["com.example.game"], "Game")

    def test_ignores_non_package_strings(self) -> None:
        self.assertEqual(_extract_apps({"status": "ok", "count": 3}), [])


class SettingsStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "settings.json"
        self.store = SettingsStore(self.path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_round_trip(self) -> None:
        prefs = AppPrefs(app_package="com.whatsapp", auto_open_app=True)
        self.store.save(prefs)
        self.assertTrue(self.path.is_file())

        loaded = SettingsStore(self.path).load()
        self.assertEqual(loaded.app_package, "com.whatsapp")
        self.assertTrue(loaded.auto_open_app)

    def test_missing_file_uses_env_defaults(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "MUMU_AUTO_APP_PACKAGE": "com.example.app",
                "MUMU_AUTO_OPEN_APP": "true",
            },
        ):
            loaded = self.store.load()
        self.assertEqual(loaded.app_package, "com.example.app")
        self.assertTrue(loaded.auto_open_app)

    def test_invalid_file_returns_defaults(self) -> None:
        self.path.write_text("bukan json", encoding="utf-8")
        loaded = self.store.load()
        self.assertEqual(loaded.app_package, "")
        self.assertFalse(loaded.auto_open_app)


if __name__ == "__main__":
    unittest.main()
