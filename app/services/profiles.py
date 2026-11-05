"""Preset bawaan dan profil custom."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app import models

logger = logging.getLogger(__name__)

BUILTIN_PROFILES: dict[str, dict[str, str]] = {
    "Hemat": {
        "resolution_mode": "phone.3",
        "performance_mode": "low",
        "performance_cpu.custom": "1",
        "performance_mem.custom": "1.000000",
        "max_frame_rate": "30",
        "dynamic_adjust_frame_rate": "true",
        "dynamic_low_frame_rate_limit": "15",
        "vertical_sync": "false",
        "renderer_mode": "dx",
        "renderer_strategy": "perf",
        "force_discrete_graphics": "false",
    },
    "Seimbang": {
        "resolution_mode": "phone.2",
        "performance_mode": "middle",
        "performance_cpu.custom": "4",
        "performance_mem.custom": "3.000000",
        "max_frame_rate": "60",
        "dynamic_adjust_frame_rate": "false",
        "dynamic_low_frame_rate_limit": "30",
        "vertical_sync": "true",
        "renderer_mode": "dx",
        "renderer_strategy": "auto",
        "force_discrete_graphics": "true",
    },
    "Performa": {
        "resolution_mode": "phone.0",
        "performance_mode": "high",
        "performance_cpu.custom": "6",
        "performance_mem.custom": "4.000000",
        "max_frame_rate": "120",
        "dynamic_adjust_frame_rate": "false",
        "dynamic_low_frame_rate_limit": "30",
        "vertical_sync": "false",
        "renderer_mode": "vk",
        "renderer_strategy": "perf",
        "force_discrete_graphics": "true",
    },
}


def default_store_path() -> Path:
    appdata = os.getenv("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".config"
    return base / "mumu-quick-tuner" / "profiles.json"


class ProfileStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_store_path()

    def load_custom(self) -> dict[str, dict[str, str]]:
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Gagal membaca profil %s: %s", self.path, exc)
            return {}

        profiles: dict[str, dict[str, str]] = {}
        if isinstance(data, dict):
            for name, changes in data.items():
                if isinstance(changes, dict):
                    profiles[str(name)] = {
                        str(k): str(v) for k, v in changes.items()
                    }
        return profiles

    def save_custom(self, name: str, changes: dict[str, str]) -> None:
        profiles = self.load_custom()
        profiles[name] = models.filter_managed(changes)
        self._write(profiles)

    def delete_custom(self, name: str) -> None:
        profiles = self.load_custom()
        if name in profiles:
            del profiles[name]
            self._write(profiles)

    def rename(self, old: str, new: str) -> str:
        new = new.strip()
        if not new:
            raise ValueError("Nama preset tidak boleh kosong.")
        if old in BUILTIN_PROFILES:
            raise ValueError("Preset bawaan tidak bisa diganti namanya.")
        profiles = self.load_custom()
        if old not in profiles:
            raise ValueError(f"Preset '{old}' tidak ditemukan.")
        if new in BUILTIN_PROFILES or new in profiles:
            raise ValueError(f"Preset '{new}' sudah ada.")
        changes = profiles.pop(old)
        profiles[new] = changes
        self._write(profiles)
        return new

    def get(self, name: str) -> dict[str, str] | None:
        if name in BUILTIN_PROFILES:
            return dict(BUILTIN_PROFILES[name])
        custom = self.load_custom()
        if name in custom:
            return dict(custom[name])
        return None

    def is_builtin(self, name: str) -> bool:
        return name in BUILTIN_PROFILES

    def _write(self, profiles: dict[str, dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(profiles, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(self.path)

    def all_profiles(self) -> list[tuple[str, dict[str, str], bool]]:
        items: list[tuple[str, dict[str, str], bool]] = [
            (name, dict(changes), True)
            for name, changes in BUILTIN_PROFILES.items()
        ]
        items.extend(
            (name, changes, False)
            for name, changes in self.load_custom().items()
        )
        return items
