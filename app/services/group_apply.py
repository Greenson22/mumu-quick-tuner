"""Eksekusi batch: terapkan preset ke beberapa device secara berurutan."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app import models
from app.mumu import MuMuClient
from app.services.backup import create_backup

ProgressCallback = Callable[[dict], None]


@dataclass
class BatchResult:
    name: str
    index: str
    status: str  # success | unchanged | failed | skipped
    message: str = ""
    changed: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in {"success", "unchanged"}


def prepare_preset(preset: dict[str, str] | None) -> dict[str, str]:
    """Batasi preset ke key yang dikelola aplikasi."""
    if not preset:
        return {}
    return {
        str(key): str(value)
        for key, value in preset.items()
        if key in models.MANAGED_KEYS
    }


def diff_settings(
    current: dict[str, str], preset: dict[str, str]
) -> dict[str, str]:
    return {
        key: str(value)
        for key, value in preset.items()
        if str(current.get(key, "")) != str(value)
    }


def _emit(
    progress: ProgressCallback | None,
    name: str,
    index: str,
    phase: str,
    message: str = "",
    status: str = "",
) -> None:
    if progress is None:
        return
    progress(
        {
            "name": name,
            "index": str(index),
            "phase": phase,
            "message": message,
            "status": status,
        }
    )


def run_batch(
    client: MuMuClient,
    targets: list[tuple[str, str]],
    preset: dict[str, str],
    backup_dir: Path,
    progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[BatchResult]:
    """Terapkan preset ke daftar (name, index) secara berurutan.

    Device yang gagal tidak menghentikan device berikutnya.
    """
    preset = prepare_preset(preset)
    results: list[BatchResult] = []

    for name, index in targets:
        if should_cancel is not None and should_cancel():
            results.append(
                BatchResult(name, str(index), "skipped", "Dibatalkan pengguna.")
            )
            _emit(progress, name, index, "skip", "Dibatalkan.", "skipped")
            continue

        try:
            _emit(progress, name, index, "read", "Membaca setting…")
            current = client.get_settings(index)
            changes = diff_settings(current, preset)

            if not changes:
                results.append(
                    BatchResult(name, str(index), "unchanged", "Sudah sama.")
                )
                _emit(progress, name, index, "unchanged", "Sudah sama.", "unchanged")
                continue

            _emit(progress, name, index, "backup", "Membuat backup…")
            backup = create_backup(current, backup_dir)
            if backup:
                _emit(progress, name, index, "backup", f"Backup: {backup.name}")

            _emit(progress, name, index, "apply", "Menerapkan setting…")
            client.apply(index, changes)

            _emit(progress, name, index, "verify", "Memverifikasi…")
            verified = client.get_settings(index)
            mismatches = {
                key: value
                for key, value in changes.items()
                if str(verified.get(key, "")) != str(value)
            }

            if mismatches:
                detail = ", ".join(mismatches.keys())
                results.append(
                    BatchResult(
                        name,
                        str(index),
                        "failed",
                        f"Verifikasi gagal pada: {detail}",
                        changes,
                    )
                )
                _emit(
                    progress,
                    name,
                    index,
                    "error",
                    f"Verifikasi gagal: {detail}",
                    "failed",
                )
                continue

            results.append(
                BatchResult(
                    name,
                    str(index),
                    "success",
                    f"{len(changes)} setting diubah.",
                    changes,
                )
            )
            _emit(
                progress,
                name,
                index,
                "done",
                f"Selesai ({len(changes)} setting).",
                "success",
            )

        except Exception as exc:  # noqa: BLE001 - dilaporkan per device
            results.append(
                BatchResult(name, str(index), "failed", str(exc))
            )
            _emit(progress, name, index, "error", str(exc), "failed")

    return results
