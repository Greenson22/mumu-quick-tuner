"""Pembacaan konfigurasi aplikasi dari file .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Muat .env tanpa mewajibkan python-dotenv (ada fallback parser)."""
    try:
        from dotenv import load_dotenv

        load_dotenv(path, override=False)
        return
    except ImportError:
        pass

    if not path.is_file():
        return

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    manager: Path
    vm_name: str
    vm_index: str | None
    backup_dir: Path
    log_level: str


def load_config() -> AppConfig:
    root = Path(__file__).resolve().parent.parent
    _load_dotenv(root / ".env")

    manager = Path(
        os.getenv(
            "MUMU_MANAGER",
            r"C:\Program Files\Netease\MuMuPlayer\nx_main\MuMuManager.exe",
        )
    )

    backup_raw = os.getenv("MUMU_BACKUP_DIR", "backups").strip() or "backups"
    backup_dir = Path(backup_raw)
    if not backup_dir.is_absolute():
        backup_dir = root / backup_dir

    index_raw = os.getenv("MUMU_VM_INDEX", "").strip()
    vm_index = index_raw or None

    return AppConfig(
        project_root=root,
        manager=manager,
        vm_name=os.getenv("MUMU_VM_NAME", "").strip(),
        vm_index=vm_index,
        backup_dir=backup_dir,
        log_level=os.getenv("MUMU_LOG_LEVEL", "INFO").strip().upper(),
    )
