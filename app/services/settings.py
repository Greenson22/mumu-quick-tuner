"""Preferensi aplikasi (paket aplikasi yang dibuka otomatis)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


def default_settings_path() -> Path:
    appdata = os.getenv("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".config"
    return base / "mumu-quick-tuner" / "settings.json"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "ya", "on"}


@dataclass
class AppPrefs:
    app_package: str = ""
    auto_open_app: bool = False

    def to_dict(self) -> dict:
        return {
            "app_package": self.app_package,
            "auto_open_app": self.auto_open_app,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppPrefs":
        return cls(
            app_package=str(data.get("app_package", "")).strip(),
            auto_open_app=bool(data.get("auto_open_app", False)),
        )


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_settings_path()

    def load(self) -> AppPrefs:
        if not self.path.is_file():
            return AppPrefs(
                app_package=os.getenv("MUMU_AUTO_APP_PACKAGE", "").strip(),
                auto_open_app=_env_bool("MUMU_AUTO_OPEN_APP"),
            )

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Gagal membaca %s", self.path, exc_info=True)
            return AppPrefs()

        if not isinstance(raw, dict):
            return AppPrefs()
        return AppPrefs.from_dict(raw)

    def save(self, prefs: AppPrefs) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(prefs.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            logger.warning("Gagal menyimpan %s", self.path, exc_info=True)
