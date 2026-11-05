"""Tes penyimpanan dan resolusi grup device."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.services.groups import DeviceRef, GroupStore


class GroupStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "groups.json"
        self.store = GroupStore(self.path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_create_and_persist(self) -> None:
        group = self.store.create(
            "Kelas 10A",
            [DeviceRef("a@guru.sd.belajar.id", "2"), DeviceRef("b@guru.sd.belajar.id", "5")],
        )
        self.assertEqual(group.name, "Kelas 10A")
        self.assertTrue(self.path.is_file())

        reloaded = GroupStore(self.path).get("Kelas 10A")
        self.assertIsNotNone(reloaded)
        assert reloaded is not None
        self.assertEqual(
            [device.name for device in reloaded.devices],
            ["a@guru.sd.belajar.id", "b@guru.sd.belajar.id"],
        )

    def test_duplicate_group_rejected(self) -> None:
        self.store.create("Grup", [DeviceRef("a")])
        with self.assertRaises(ValueError):
            self.store.create("Grup", [DeviceRef("b")])
        with self.assertRaises(ValueError):
            self.store.create("   ", [DeviceRef("b")])

    def test_add_devices_is_unique(self) -> None:
        self.store.create("Grup", [DeviceRef("a")])
        self.store.add_devices("Grup", [DeviceRef("a"), DeviceRef("b")])
        group = self.store.get("Grup")
        assert group is not None
        self.assertEqual([device.name for device in group.devices], ["a", "b"])

    def test_remove_devices(self) -> None:
        self.store.create("Grup", [DeviceRef("a"), DeviceRef("b")])
        group = self.store.remove_devices("Grup", ["a"])
        self.assertEqual([device.name for device in group.devices], ["b"])

    def test_rename_and_delete(self) -> None:
        self.store.create("Lama", [DeviceRef("a")])
        self.store.create("Lain", [DeviceRef("b")])
        self.assertEqual(self.store.rename("Lama", "Baru"), "Baru")
        self.assertIsNone(self.store.get("Lama"))
        self.assertIsNotNone(self.store.get("Baru"))
        with self.assertRaises(ValueError):
            self.store.rename("Baru", "Lain")

        self.store.delete("Baru")
        self.assertIsNone(self.store.get("Baru"))

    def test_set_last_preset(self) -> None:
        self.store.create("Grup", [DeviceRef("a")])
        self.store.set_last_preset("Grup", "Hemat")
        group = self.store.get("Grup")
        assert group is not None
        self.assertEqual(group.last_preset, "Hemat")

    def test_resolve_uses_name_not_index(self) -> None:
        self.store.create("Grup", [DeviceRef("a", "2"), DeviceRef("b", "5")])
        available = {
            "1": {"name": "b"},
            "7": {"name": "a"},
            "9": {"name": "lain"},
        }
        found, missing = self.store.resolve("Grup", available)

        self.assertEqual(
            [(index, name) for index, name, _device in found],
            [("7", "a"), ("1", "b")],
        )
        self.assertEqual(missing, [])

    def test_resolve_missing_device(self) -> None:
        self.store.create("Grup", [DeviceRef("a"), DeviceRef("hilang")])
        found, missing = self.store.resolve("Grup", {"3": {"name": "a"}})
        self.assertEqual(len(found), 1)
        self.assertEqual([ref.name for ref in missing], ["hilang"])

    def test_membership_iteration(self) -> None:
        self.store.create("A", [DeviceRef("dev")])
        self.store.create("B", [DeviceRef("dev"), DeviceRef("lain")])
        self.assertEqual(self.store.groups_for_device("dev"), ["A", "B"])

    def test_corrupt_file_returns_empty(self) -> None:
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.store.load(), {})

    def test_file_is_valid_json(self) -> None:
        self.store.create("Grup", [DeviceRef("a", "2")])
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["groups"]["Grup"]["devices"][0]["name"], "a")


if __name__ == "__main__":
    unittest.main()
