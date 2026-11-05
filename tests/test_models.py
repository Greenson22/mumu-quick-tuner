"""Tes unit untuk helper yang tidak membutuhkan PyQt6/MuMu."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app import models
from app.services.backup import resolve_vm_dir
from app.services.profiles import BUILTIN_PROFILES, ProfileStore


class ModelTests(unittest.TestCase):
    def test_parse_number_list(self) -> None:
        self.assertEqual(
            models.parse_number_list("[1,2,3](best=2)"), [1.0, 2.0, 3.0]
        )
        self.assertEqual(models.parse_number_list(""), [])

    def test_parse_best(self) -> None:
        self.assertEqual(models.parse_best("[1,2,3](best=2)"), 2.0)
        self.assertIsNone(models.parse_best("[1,2]"))

    def test_bool(self) -> None:
        self.assertTrue(models.as_bool("true"))
        self.assertFalse(models.as_bool("false"))
        self.assertEqual(models.bool_str(True), "true")

    def test_format_ram(self) -> None:
        self.assertEqual(models.format_ram("0.750000"), "0.75 GB (768 MB)")
        self.assertEqual(models.format_ram("3.000000"), "3 GB (3072 MB)")

    def test_describe_value(self) -> None:
        self.assertEqual(models.describe_value("renderer_mode", "vk"), "Vulkan")
        self.assertEqual(
            models.describe_value("performance_mode", "low"), "Low (hemat)"
        )


class ProfileTests(unittest.TestCase):
    def test_builtin_profiles_exist(self) -> None:
        self.assertIn("Hemat", BUILTIN_PROFILES)
        self.assertIn("Seimbang", BUILTIN_PROFILES)
        self.assertIn("Performa", BUILTIN_PROFILES)

    def test_custom_profile_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ProfileStore(Path(tmp) / "profiles.json")
            store.save_custom("Tes", {"max_frame_rate": "60"})
            self.assertEqual(store.load_custom()["Tes"]["max_frame_rate"], "60")
            store.delete_custom("Tes")
            self.assertNotIn("Tes", store.load_custom())

    def test_profile_file_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profiles.json"
            store = ProfileStore(path)
            store.save_custom("A", {"vertical_sync": "true"})
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["A"]["vertical_sync"], "true")

    def test_get_builtin_and_custom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ProfileStore(Path(tmp) / "profiles.json")
            self.assertIsNotNone(store.get("Hemat"))
            self.assertIsNone(store.get("TidakAda"))

            store.save_custom("Malam", {"max_frame_rate": "60"})
            self.assertEqual(store.get("Malam"), {"max_frame_rate": "60"})

    def test_save_custom_filters_unmanaged_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ProfileStore(Path(tmp) / "profiles.json")
            store.save_custom(
                "Aman",
                {
                    "max_frame_rate": "60",
                    "player_name": "Jangan diubah",
                    "phone_imei": "123",
                },
            )
            self.assertEqual(store.get("Aman"), {"max_frame_rate": "60"})

    def test_rename_custom_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ProfileStore(Path(tmp) / "profiles.json")
            store.save_custom("Lama", {"max_frame_rate": "60"})
            self.assertEqual(store.rename("Lama", "Baru"), "Baru")
            self.assertIsNone(store.get("Lama"))
            self.assertEqual(store.get("Baru"), {"max_frame_rate": "60"})
            with self.assertRaises(ValueError):
                store.rename("Baru", "Hemat")


class BackupTests(unittest.TestCase):
    def test_resolve_vm_dir(self) -> None:
        settings = {
            "device_thumbnail": (
                r"C:\Program Files\Netease\MuMuPlayer\vms"
                r"\MuMuPlayerGlobal-15.0-2\private_shared\boot_screenshot.png"
            )
        }
        self.assertEqual(
            resolve_vm_dir(settings),
            Path(
                r"C:\Program Files\Netease\MuMuPlayer\vms"
                r"\MuMuPlayerGlobal-15.0-2"
            ),
        )

    def test_resolve_vm_dir_empty(self) -> None:
        self.assertIsNone(resolve_vm_dir({}))


if __name__ == "__main__":
    unittest.main()
