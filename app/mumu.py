"""Wrapper tipis untuk MuMuManager.exe (CLI resmi MuMu Player)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


class MuMuError(RuntimeError):
    """Kesalahan yang berasal dari MuMuManager atau proses pemanggilannya."""


def _no_window_flag() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0


def pick_device(
    devices: dict[str, dict], name: str, index: str | None = None
) -> tuple[str, dict]:
    """Pilih device dari hasil info -v all berdasarkan index atau nama."""
    if index:
        if str(index) in devices:
            return str(index), devices[str(index)]
        raise MuMuError(f"Device dengan index {index} tidak ditemukan.")

    if not name:
        raise MuMuError(
            "MUMU_VM_NAME kosong di .env dan MUMU_VM_INDEX tidak diisi."
        )

    for idx, device in devices.items():
        if str(device.get("name", "")).strip() == name:
            return str(idx), device

    available = ", ".join(
        f"{idx}:{device.get('name', '?')}" for idx, device in devices.items()
    )
    raise MuMuError(
        f"Device bernama '{name}' tidak ditemukan.\n\nDevice tersedia: {available}"
    )


class MuMuClient:
    def __init__(self, manager: Path, timeout: int = 120) -> None:
        self.manager = Path(manager)
        self.timeout = timeout

    # ------------------------------------------------------------------ core
    def _run(self, *args: str, timeout: int | None = None) -> dict:
        if not self.manager.is_file():
            raise MuMuError(
                "MuMuManager.exe tidak ditemukan:\n"
                f"{self.manager}\n\nPeriksa MUMU_MANAGER di file .env."
            )

        cmd = [str(self.manager), *args]

        # MuMuManager adalah aplikasi Qt. Kalau variabel platform Qt ikut
        # terwarisi (mis. QT_QPA_PLATFORM=offscreen), prosesnya bisa menggantung.
        env = os.environ.copy()
        for key in (
            "QT_QPA_PLATFORM",
            "QT_QPA_PLATFORM_PLUGIN_PATH",
            "QT_PLUGIN_PATH",
        ):
            env.pop(key, None)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout or self.timeout,
                creationflags=_no_window_flag(),
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise MuMuError(
                f"MuMuManager tidak merespons dalam {timeout or self.timeout} detik."
            ) from exc
        except OSError as exc:
            raise MuMuError(f"Gagal menjalankan MuMuManager: {exc}") from exc

        stdout = (proc.stdout or "").lstrip("\ufeff").strip()
        stderr = (proc.stderr or "").strip()

        if not stdout:
            detail = stderr or f"exit code {proc.returncode}"
            raise MuMuError(f"MuMuManager tidak mengembalikan data ({detail}).")

        start = stdout.find("{")
        if start > 0:
            stdout = stdout[start:]

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            snippet = stdout[:300]
            raise MuMuError(f"Output MuMuManager bukan JSON:\n{snippet}") from exc

        if not isinstance(data, dict):
            raise MuMuError("Format output MuMuManager tidak dikenali.")

        code = data.get("errcode")
        if code not in (None, 0):
            message = data.get("errmsg") or "Terjadi kesalahan pada MuMuManager."
            raise MuMuError(f"{message} (kode {code})")

        return data

    # --------------------------------------------------------------- queries
    def list_devices(self) -> dict[str, dict]:
        data = self._run("info", "-v", "all")
        devices: dict[str, dict] = {}
        for key, value in data.items():
            if isinstance(value, dict):
                devices[str(key)] = value
        return devices

    def find_device(self, name: str, index: str | None = None) -> tuple[str, dict]:
        return pick_device(self.list_devices(), name, index)

    def get_info(self, index: str) -> dict:
        return self._run("info", "-v", str(index))

    def get_settings(self, index: str) -> dict[str, str]:
        data = self._run("setting", "-v", str(index), "--all")
        return {str(k): ("" if v is None else str(v)) for k, v in data.items()}

    def get_key_info(self, index: str, keys: list[str]) -> dict:
        args = ["setting", "-v", str(index), "-i"]
        for key in keys:
            args += ["-k", key]
        return self._run(*args)

    # --------------------------------------------------------------- actions
    def apply(self, index: str, changes: dict[str, str]) -> None:
        if not changes:
            return

        args = ["setting", "-v", str(index)]
        for key, value in changes.items():
            args += ["--key", str(key), "--value", str(value)]
        self._run(*args)

    def control(self, index: str, action: str) -> None:
        self._run("control", "-v", str(index), action)

    def wait_stopped(self, index: str, timeout: int = 45) -> bool:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            info = self.get_info(index)
            if not info.get("is_process_started", False):
                return True
            time.sleep(1.0)
        return False
