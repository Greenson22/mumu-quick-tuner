"""Model, penyimpanan, dan laporan fitur otomatisasi grup."""

from __future__ import annotations

import json
import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 3
DEFAULT_DURATION_MIN_SEC = 240
DEFAULT_DURATION_MAX_SEC = 360
DEFAULT_REFERENCE_WIDTH = 1280
DEFAULT_REFERENCE_HEIGHT = 720

STEP_ACTIONS = ("tap", "swipe", "wait", "key")
KEY_NAMES = {
    "back": 4,
    "home": 3,
    "task": 187,
    "enter": 66,
    "delete": 67,
}
KEY_LABELS = {
    "back": "Back",
    "home": "Home",
    "task": "Recent apps",
    "enter": "Enter",
    "delete": "Delete",
}


def default_automation_path() -> Path:
    appdata = os.getenv("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".config"
    return base / "mumu-quick-tuner" / "automation.json"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def looks_like_package(value: str) -> bool:
    value = value.strip()
    return "." in value and " " not in value


@dataclass
class ScriptStep:
    """Satu langkah interaksi otomatis."""

    action: str = "tap"
    x: int = 0
    y: int = 0
    x2: int = 0
    y2: int = 0
    duration_ms: int = 300
    key: str = "back"
    delay_ms: int = 500

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "x": self.x,
            "y": self.y,
            "x2": self.x2,
            "y2": self.y2,
            "duration_ms": self.duration_ms,
            "key": self.key,
            "delay_ms": self.delay_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScriptStep":
        action = str(data.get("action", "tap")).strip().lower()
        if action not in STEP_ACTIONS:
            action = "tap"
        key = str(data.get("key", "back")).strip().lower()
        if key not in KEY_NAMES:
            key = "back"
        return cls(
            action=action,
            x=_to_int(data.get("x")),
            y=_to_int(data.get("y")),
            x2=_to_int(data.get("x2")),
            y2=_to_int(data.get("y2")),
            duration_ms=max(0, _to_int(data.get("duration_ms"), 300)),
            key=key,
            delay_ms=max(0, _to_int(data.get("delay_ms"), 500)),
        )

    def validation_error(self) -> str | None:
        if self.action == "tap":
            if self.x < 0 or self.y < 0:
                return "Koordinat tap tidak boleh negatif."
        elif self.action == "swipe":
            if min(self.x, self.y, self.x2, self.y2) < 0:
                return "Koordinat swipe tidak boleh negatif."
            if self.duration_ms < 50:
                return "Durasi swipe minimal 50 ms."
        elif self.action == "wait":
            if self.delay_ms < 0:
                return "Jeda tunggu tidak boleh negatif."
        elif self.action == "key":
            if self.key not in KEY_NAMES:
                return f"Tombol '{self.key}' tidak dikenali."
        return None

    def describe(self) -> str:
        if self.action == "tap":
            return f"Tap ({self.x}, {self.y})"
        if self.action == "swipe":
            return (
                f"Swipe ({self.x}, {self.y}) → ({self.x2}, {self.y2}) "
                f"{self.duration_ms} ms"
            )
        if self.action == "wait":
            return f"Tunggu {self.delay_ms} ms"
        return f"Tombol {KEY_LABELS.get(self.key, self.key)}"


@dataclass
class AutomationApp:
    package: str
    label: str = ""
    enabled: bool = True
    steps: list[ScriptStep] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "package": self.package,
            "label": self.label,
            "enabled": self.enabled,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AutomationApp":
        package = str(data.get("package", "")).strip()
        steps: list[ScriptStep] = []
        raw_steps = data.get("steps", [])
        if isinstance(raw_steps, list):
            for item in raw_steps:
                if isinstance(item, dict):
                    steps.append(ScriptStep.from_dict(item))
        return cls(
            package=package,
            label=str(data.get("label", "")).strip(),
            enabled=bool(data.get("enabled", True)),
            steps=steps,
        )

    @property
    def display_name(self) -> str:
        return self.label or self.package


@dataclass
class AutomationConfig:
    batch_size: int = DEFAULT_BATCH_SIZE
    duration_min_sec: int = DEFAULT_DURATION_MIN_SEC
    duration_max_sec: int = DEFAULT_DURATION_MAX_SEC
    interaction_enabled: bool = True
    scale_coordinates: bool = True
    reference_width: int = DEFAULT_REFERENCE_WIDTH
    reference_height: int = DEFAULT_REFERENCE_HEIGHT
    apps: list[AutomationApp] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "batch_size": self.batch_size,
            "duration_min_sec": self.duration_min_sec,
            "duration_max_sec": self.duration_max_sec,
            "interaction_enabled": self.interaction_enabled,
            "scale_coordinates": self.scale_coordinates,
            "reference_resolution": [self.reference_width, self.reference_height],
            "apps": [app.to_dict() for app in self.apps],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AutomationConfig":
        raw_resolution = data.get("reference_resolution", [])
        if isinstance(raw_resolution, (list, tuple)) and len(raw_resolution) >= 2:
            width = _to_int(raw_resolution[0], DEFAULT_REFERENCE_WIDTH)
            height = _to_int(raw_resolution[1], DEFAULT_REFERENCE_HEIGHT)
        else:
            width = _to_int(
                data.get("reference_width"), DEFAULT_REFERENCE_WIDTH
            )
            height = _to_int(
                data.get("reference_height"), DEFAULT_REFERENCE_HEIGHT
            )

        apps: list[AutomationApp] = []
        raw_apps = data.get("apps", [])
        if isinstance(raw_apps, list):
            for item in raw_apps:
                if isinstance(item, dict):
                    app = AutomationApp.from_dict(item)
                    if app.package:
                        apps.append(app)

        return cls(
            batch_size=max(1, _to_int(data.get("batch_size"), DEFAULT_BATCH_SIZE)),
            duration_min_sec=max(
                1, _to_int(data.get("duration_min_sec"), DEFAULT_DURATION_MIN_SEC)
            ),
            duration_max_sec=max(
                1, _to_int(data.get("duration_max_sec"), DEFAULT_DURATION_MAX_SEC)
            ),
            interaction_enabled=bool(data.get("interaction_enabled", True)),
            scale_coordinates=bool(data.get("scale_coordinates", True)),
            reference_width=max(1, width),
            reference_height=max(1, height),
            apps=apps,
        )

    def enabled_apps(self) -> list[AutomationApp]:
        return [app for app in self.apps if app.enabled and app.package]

    def validation_error(self) -> str | None:
        if self.batch_size < 1:
            return "Jumlah device per batch minimal 1."
        if self.duration_min_sec < 1:
            return "Durasi minimum minimal 1 detik."
        if self.duration_min_sec > self.duration_max_sec:
            return "Durasi minimum tidak boleh lebih besar dari durasi maksimum."
        if self.reference_width < 1 or self.reference_height < 1:
            return "Resolusi referensi script tidak valid."
        enabled = self.enabled_apps()
        if not enabled:
            return "Aktifkan minimal satu aplikasi otomatisasi."
        seen: set[str] = set()
        for app in enabled:
            if not looks_like_package(app.package):
                return (
                    f"Paket aplikasi '{app.package}' tidak valid. "
                    "Contoh: com.whatsapp"
                )
            if app.package in seen:
                return f"Aplikasi '{app.package}' muncul lebih dari sekali."
            seen.add(app.package)
            for index, step in enumerate(app.steps, start=1):
                error = step.validation_error()
                if error:
                    return f"{app.display_name}, langkah {index}: {error}"
        return None

    def choose_duration(self, rng: random.Random | None = None) -> int:
        generator = rng or random
        low = min(self.duration_min_sec, self.duration_max_sec)
        high = max(self.duration_min_sec, self.duration_max_sec)
        return generator.randint(low, high)


class AutomationStore:
    """Penyimpanan konfigurasi otomatisasi global."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_automation_path()

    def load(self) -> AutomationConfig:
        if not self.path.is_file():
            return AutomationConfig()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Gagal membaca %s", self.path, exc_info=True)
            return AutomationConfig()
        if not isinstance(raw, dict):
            return AutomationConfig()
        return AutomationConfig.from_dict(raw)

    def save(self, config: AutomationConfig) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(config.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(self.path)
        except OSError:
            logger.warning("Gagal menyimpan %s", self.path, exc_info=True)

    def seed_from_package(self, package: str) -> AutomationConfig:
        """Isi daftar aplikasi dari paket lama saat file belum pernah dibuat."""
        config = self.load()
        package = package.strip()
        if self.path.exists():
            return config
        if package and looks_like_package(package):
            config.apps.append(AutomationApp(package=package, enabled=True))
            self.save(config)
        return config


# --------------------------------------------------------------------- report
@dataclass
class DeviceReport:
    name: str
    index: str
    batch: int = 1
    status: str = "skipped"  # success | failed | skipped | stopped
    message: str = ""
    apps_opened: list[str] = field(default_factory=list)
    apps_missing: list[str] = field(default_factory=list)
    script_errors: list[str] = field(default_factory=list)
    duration_sec: int = 0
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "index": self.index,
            "batch": self.batch,
            "status": self.status,
            "message": self.message,
            "apps_opened": list(self.apps_opened),
            "apps_missing": list(self.apps_missing),
            "script_errors": list(self.script_errors),
            "duration_sec": self.duration_sec,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass
class AutomationReport:
    group: str
    batch_size: int
    duration_min_sec: int
    duration_max_sec: int
    interaction_enabled: bool
    devices: list[DeviceReport] = field(default_factory=list)
    started_at: str = field(default_factory=_now_iso)
    finished_at: str = ""
    stopped_by_user: bool = False
    report_path: str = ""

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for device in self.devices:
            counts[device.status] = counts.get(device.status, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "group": self.group,
            "batch_size": self.batch_size,
            "duration_min_sec": self.duration_min_sec,
            "duration_max_sec": self.duration_max_sec,
            "interaction_enabled": self.interaction_enabled,
            "started_at": self.started_at,
            "finished_at": self.finished_at or _now_iso(),
            "stopped_by_user": self.stopped_by_user,
            "counts": self.counts(),
            "devices": [device.to_dict() for device in self.devices],
        }

    def summary_text(self) -> str:
        counts = self.counts()
        if self.duration_max_sec < 60:
            duration_label = f"{self.duration_min_sec}–{self.duration_max_sec} detik"
        else:
            duration_label = (
                f"{self.duration_min_sec / 60:g}–"
                f"{self.duration_max_sec / 60:g} menit"
            )
        lines = [
            f"Grup: {self.group}",
            f"Batch size: {self.batch_size} device",
            f"Durasi per device: {duration_label}",
            "Interaksi otomatis: "
            + ("aktif" if self.interaction_enabled else "nonaktif"),
            "",
            f"Berhasil: {counts.get('success', 0)}",
            f"Gagal: {counts.get('failed', 0)}",
            f"Dilewati: {counts.get('skipped', 0)}",
            f"Dihentikan: {counts.get('stopped', 0)}",
        ]
        if self.stopped_by_user:
            lines.append("\nSesi dihentikan oleh pengguna.")
        failed = [device for device in self.devices if device.status == "failed"]
        if failed:
            lines.append("\nDevice gagal:")
            for device in failed[:12]:
                lines.append(f"• {device.name}: {device.message}")
            if len(failed) > 12:
                lines.append(f"… dan {len(failed) - 12} device lain.")
        if self.report_path:
            lines.append(f"\nLaporan disimpan di:\n{self.report_path}")
        return "\n".join(lines)


def write_report(report: AutomationReport, report_dir: Path) -> Path:
    """Tulis laporan JSON dan kembalikan path-nya."""
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = report_dir / f"automation-{stamp}.json"
    counter = 1
    while path.exists():
        path = report_dir / f"automation-{stamp}-{counter}.json"
        counter += 1
    report.finished_at = report.finished_at or _now_iso()
    path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    report.report_path = str(path)
    return path
