"""Penyimpanan grup device (berdasarkan nama device, bukan index)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def default_groups_path() -> Path:
    appdata = os.getenv("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".config"
    return base / "mumu-quick-tuner" / "groups.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class DeviceRef:
    name: str
    index: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "index": str(self.index)}

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceRef":
        return cls(
            name=str(data.get("name", "")).strip(),
            index=str(data.get("index", "")).strip(),
        )


@dataclass
class DeviceGroup:
    name: str
    devices: list[DeviceRef] = field(default_factory=list)
    last_preset: str | None = None
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "devices": [device.to_dict() for device in self.devices],
            "last_preset": self.last_preset,
            "updated_at": self.updated_at or _now(),
        }

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "DeviceGroup":
        devices: list[DeviceRef] = []
        raw_devices = data.get("devices", [])
        if isinstance(raw_devices, list):
            for item in raw_devices:
                if isinstance(item, dict):
                    ref = DeviceRef.from_dict(item)
                    if ref.name:
                        devices.append(ref)
        return cls(
            name=name,
            devices=devices,
            last_preset=(str(data["last_preset"]) if data.get("last_preset") else None),
            updated_at=str(data.get("updated_at", "")),
        )


class GroupStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_groups_path()

    # ------------------------------------------------------------------ io
    def load(self) -> dict[str, DeviceGroup]:
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Gagal membaca grup %s: %s", self.path, exc)
            return {}

        groups: dict[str, DeviceGroup] = {}
        raw = data.get("groups", {}) if isinstance(data, dict) else {}
        if isinstance(raw, dict):
            for name, item in raw.items():
                if isinstance(item, dict):
                    groups[str(name)] = DeviceGroup.from_dict(str(name), item)
        return groups

    def _write(self, groups: dict[str, DeviceGroup]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "groups": {name: group.to_dict() for name, group in groups.items()},
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(self.path)

    # --------------------------------------------------------------- crud
    def get(self, name: str) -> DeviceGroup | None:
        return self.load().get(name)

    def names(self) -> list[str]:
        return list(self.load().keys())

    def create(self, name: str, devices: list[DeviceRef]) -> DeviceGroup:
        name = name.strip()
        if not name:
            raise ValueError("Nama grup tidak boleh kosong.")
        groups = self.load()
        if name in groups:
            raise ValueError(f"Grup '{name}' sudah ada.")
        group = DeviceGroup(
            name=name,
            devices=self._unique(devices),
            updated_at=_now(),
        )
        groups[name] = group
        self._write(groups)
        return group

    def add_devices(self, name: str, devices: list[DeviceRef]) -> DeviceGroup:
        groups = self.load()
        group = groups.get(name)
        if group is None:
            raise ValueError(f"Grup '{name}' tidak ditemukan.")
        existing = {device.name for device in group.devices}
        for device in devices:
            if device.name not in existing:
                group.devices.append(device)
                existing.add(device.name)
        group.updated_at = _now()
        self._write(groups)
        return group

    def remove_devices(self, name: str, device_names: list[str]) -> DeviceGroup:
        groups = self.load()
        group = groups.get(name)
        if group is None:
            raise ValueError(f"Grup '{name}' tidak ditemukan.")
        remove = set(device_names)
        group.devices = [d for d in group.devices if d.name not in remove]
        group.updated_at = _now()
        self._write(groups)
        return group

    def rename(self, old: str, new: str) -> str:
        new = new.strip()
        groups = self.load()
        if old not in groups:
            raise ValueError(f"Grup '{old}' tidak ditemukan.")
        if not new:
            raise ValueError("Nama grup tidak boleh kosong.")
        if new == old:
            return old
        if new in groups:
            raise ValueError(f"Grup '{new}' sudah ada.")
        group = groups.pop(old)
        group.name = new
        group.updated_at = _now()
        groups[new] = group
        self._write(groups)
        return new

    def delete(self, name: str) -> None:
        groups = self.load()
        if name in groups:
            del groups[name]
            self._write(groups)

    def set_last_preset(self, name: str, preset: str | None) -> None:
        groups = self.load()
        group = groups.get(name)
        if group is None:
            return
        group.last_preset = preset
        group.updated_at = _now()
        self._write(groups)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _unique(devices: list[DeviceRef]) -> list[DeviceRef]:
        seen: set[str] = set()
        result: list[DeviceRef] = []
        for device in devices:
            if device.name and device.name not in seen:
                result.append(device)
                seen.add(device.name)
        return result

    def resolve(
        self, name: str, available: dict[str, dict]
    ) -> tuple[list[tuple[str, str, dict]], list[DeviceRef]]:
        """Cocokkan anggota grup ke device yang benar-benar ada.

        Returns:
            (found, missing)
            found = [(index, name, device_dict), ...]
            missing = [DeviceRef, ...]
        """
        group = self.get(name)
        if group is None:
            return [], []

        by_name = {
            str(device.get("name", "")).strip(): (str(index), device)
            for index, device in available.items()
        }

        found: list[tuple[str, str, dict]] = []
        missing: list[DeviceRef] = []
        for ref in group.devices:
            match = by_name.get(ref.name)
            if match is None:
                missing.append(ref)
            else:
                index, device = match
                found.append((index, ref.name, device))
        return found, missing

    def groups_for_device(self, device_name: str) -> list[str]:
        return [
            name
            for name, group in self.load().items()
            if any(device.name == device_name for device in group.devices)
        ]
