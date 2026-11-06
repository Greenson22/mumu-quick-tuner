"""Tes penyimpanan, validasi, dan laporan otomatisasi."""

from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path

from app.services.automation import (
    AutomationApp,
    AutomationConfig,
    AutomationReport,
    AutomationStore,
    DeviceReport,
    ScriptStep,
    write_report,
)


class AutomationStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "automation.json"
        self.store = AutomationStore(self.path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_defaults(self) -> None:
        config = self.store.load()
        self.assertEqual(config.batch_size, 3)
        self.assertEqual(config.duration_min_sec, 240)
        self.assertEqual(config.duration_max_sec, 360)
        self.assertEqual(config.apps, [])

    def test_round_trip_with_script(self) -> None:
        config = AutomationConfig(
            batch_size=2,
            duration_min_sec=120,
            duration_max_sec=180,
            interaction_enabled=True,
            reference_width=1280,
            reference_height=720,
            apps=[
                AutomationApp(
                    package="com.whatsapp",
                    label="WhatsApp",
                    enabled=True,
                    steps=[
                        ScriptStep(action="tap", x=60, y=400, delay_ms=500),
                        ScriptStep(action="wait", delay_ms=1000),
                        ScriptStep(
                            action="swipe",
                            x=10,
                            y=20,
                            x2=30,
                            y2=40,
                            duration_ms=300,
                        ),
                        ScriptStep(action="key", key="home"),
                    ],
                )
            ],
        )
        self.store.save(config)

        loaded = AutomationStore(self.path).load()
        self.assertEqual(loaded.batch_size, 2)
        self.assertEqual(loaded.duration_min_sec, 120)
        self.assertEqual(loaded.duration_max_sec, 180)
        self.assertEqual(len(loaded.apps), 1)
        self.assertEqual(loaded.apps[0].package, "com.whatsapp")
        self.assertEqual(len(loaded.apps[0].steps), 4)
        self.assertEqual(loaded.apps[0].steps[0].x, 60)
        self.assertEqual(loaded.apps[0].steps[2].duration_ms, 300)

        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(raw["version"], 1)
        self.assertEqual(raw["reference_resolution"], [1280, 720])

    def test_seed_from_old_package(self) -> None:
        self.store.seed_from_package("com.android.chrome")
        config = self.store.load()
        self.assertEqual([app.package for app in config.apps], ["com.android.chrome"])

        self.store.seed_from_package("com.whatsapp")
        config = self.store.load()
        self.assertEqual(len(config.apps), 1)

    def test_invalid_file_returns_default(self) -> None:
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.store.load().batch_size, 3)

    def test_choose_duration_within_range(self) -> None:
        config = AutomationConfig(duration_min_sec=240, duration_max_sec=360)
        rng = random.Random(1)
        values = [config.choose_duration(rng) for _ in range(200)]
        self.assertTrue(all(240 <= value <= 360 for value in values))
        self.assertTrue(len(set(values)) > 1)

    def test_report_round_trip(self) -> None:
        report = AutomationReport(
            group="Kelas",
            batch_size=3,
            duration_min_sec=240,
            duration_max_sec=360,
            interaction_enabled=True,
            devices=[
                DeviceReport(
                    name="a",
                    index="1",
                    status="success",
                    apps_opened=["com.whatsapp"],
                    duration_sec=250,
                )
            ],
        )
        path = write_report(report, Path(self._tmp.name) / "logs")
        self.assertTrue(path.is_file())
        self.assertEqual(report.report_path, str(path))

        raw = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(raw["group"], "Kelas")
        self.assertEqual(raw["counts"]["success"], 1)
        self.assertIn("Laporan disimpan di", report.summary_text())


class AutomationValidationTests(unittest.TestCase):
    def _config(self, apps: list[AutomationApp]) -> AutomationConfig:
        return AutomationConfig(apps=apps)

    def test_requires_enabled_app(self) -> None:
        config = self._config(
            [AutomationApp(package="com.whatsapp", enabled=False)]
        )
        self.assertIn("minimal satu", config.validation_error() or "")

    def test_rejects_invalid_package(self) -> None:
        config = self._config([AutomationApp(package="whatsapp")])
        self.assertIn("tidak valid", config.validation_error() or "")

    def test_rejects_duplicate_package(self) -> None:
        config = self._config(
            [
                AutomationApp(package="com.whatsapp"),
                AutomationApp(package="com.whatsapp"),
            ]
        )
        self.assertIn("lebih dari sekali", config.validation_error() or "")

    def test_rejects_bad_step(self) -> None:
        config = self._config(
            [
                AutomationApp(
                    package="com.whatsapp",
                    steps=[ScriptStep(action="swipe", duration_ms=10)],
                )
            ]
        )
        self.assertIn("Durasi swipe", config.validation_error() or "")

    def test_rejects_reversed_duration(self) -> None:
        config = AutomationConfig(
            duration_min_sec=600,
            duration_max_sec=300,
            apps=[AutomationApp(package="com.whatsapp")],
        )
        self.assertIn("minimum", config.validation_error() or "")

    def test_valid_config(self) -> None:
        config = self._config(
            [
                AutomationApp(
                    package="com.whatsapp",
                    steps=[
                        ScriptStep(action="tap", x=10, y=20),
                        ScriptStep(action="key", key="back"),
                    ],
                )
            ]
        )
        self.assertIsNone(config.validation_error())


if __name__ == "__main__":
    unittest.main()
