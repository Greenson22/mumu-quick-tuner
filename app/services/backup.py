"""Backup file konfigurasi device sebelum perubahan diterapkan."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_vm_dir(settings: dict[str, str]) -> Path | None:
    """Cari folder VM dari device_thumbnail yang dilaporkan CLI."""
    thumbnail = settings.get("device_thumbnail", "").strip()
    if not thumbnail:
        return None

    path = Path(thumbnail)
    # .../<NamaVM>/private_shared/boot_screenshot.png
    if path.parent.name.lower() == "private_shared":
        return path.parent.parent
    return path.parent


def create_backup(settings: dict[str, str], backup_root: Path) -> Path | None:
    """Salin configs/*.json dan *.nemu ke folder backup ber-timestamp."""
    vm_dir = resolve_vm_dir(settings)
    if vm_dir is None or not vm_dir.is_dir():
        logger.warning("Folder VM tidak ditemukan, backup dilewati.")
        return None

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_root / f"{vm_dir.name}-{stamp}"
    target.mkdir(parents=True, exist_ok=True)

    copied = 0
    configs = vm_dir / "configs"
    if configs.is_dir():
        for file in configs.glob("*.json"):
            shutil.copy2(file, target / file.name)
            copied += 1

    for file in vm_dir.glob("*.nemu*"):
        if file.is_file():
            shutil.copy2(file, target / file.name)
            copied += 1

    if copied == 0:
        logger.warning("Tidak ada file yang dibackup dari %s", vm_dir)
        return None

    logger.info("Backup %d file ke %s", copied, target)
    return target
