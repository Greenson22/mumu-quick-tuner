"""Wrapper tipis untuk MuMuManager.exe (CLI resmi MuMu Player)."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


class MuMuError(RuntimeError):
    """Kesalahan yang berasal dari MuMuManager atau proses pemanggilannya."""


def _no_window_flag() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0


_PACKAGE_KEYS = (
    "package",
    "package_name",
    "packageName",
    "bundle",
    "bundle_id",
    "bundleId",
)
_LABEL_KEYS = ("label", "name", "app_name", "appName", "title")


def _looks_like_package(value: str) -> bool:
    value = value.strip()
    return "." in value and " " not in value


def _extract_apps(data: object) -> list[tuple[str, str]]:
    """Ambil pasangan (package, label) dari output app info yang bervariasi."""
    found: dict[str, str] = {}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            package = ""
            for key in _PACKAGE_KEYS:
                value = node.get(key)
                if isinstance(value, str) and _looks_like_package(value):
                    package = value.strip()
                    break

            label = ""
            for key in _LABEL_KEYS:
                value = node.get(key)
                if isinstance(value, str) and value.strip():
                    label = value.strip()
                    break

            if not package:
                for key, value in node.items():
                    if not isinstance(key, str) or not _looks_like_package(key):
                        continue
                    if isinstance(value, dict):
                        package = key.strip()
                        for label_key in _LABEL_KEYS:
                            raw_label = value.get(label_key)
                            if isinstance(raw_label, str) and raw_label.strip():
                                label = raw_label.strip()
                                break
                        break
                    if isinstance(value, str):
                        package = key.strip()
                        label = label or value.strip()
                        break

            if package:
                existing = found.get(package)
                if existing is None or (label and existing == package):
                    found[package] = label or package

            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return sorted(found.items(), key=lambda item: item[1].lower())


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
    def _invoke(self, *args: str, timeout: int | None = None) -> subprocess.CompletedProcess:
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
            return subprocess.run(
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

    def _run(self, *args: str, timeout: int | None = None) -> dict:
        proc = self._invoke(*args, timeout=timeout)

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

    def _run_plain(self, *args: str, timeout: int | None = None) -> str:
        """Jalankan perintah yang output-nya teks biasa (mis. adb shell)."""
        proc = self._invoke(*args, timeout=timeout)
        stdout = (proc.stdout or "").lstrip("\ufeff").strip()
        stderr = (proc.stderr or "").strip()

        if stdout.startswith("{"):
            try:
                data = json.loads(stdout)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict) and "errcode" in data:
                if data.get("errcode") not in (None, 0):
                    message = data.get("errmsg") or "Perintah ADB gagal."
                    raise MuMuError(str(message))
                for key in ("data", "result", "output"):
                    value = data.get(key)
                    if isinstance(value, str):
                        return value.strip()

        if proc.returncode != 0 and not stdout:
            detail = stderr or f"exit code {proc.returncode}"
            raise MuMuError(f"Perintah MuMuManager gagal ({detail}).")

        return stdout

    def adb_shell(self, index: str, command: str, timeout: int = 60) -> str:
        """Jalankan perintah shell Android lewat MuMuManager."""
        command = command.strip()
        if not command:
            raise MuMuError("Perintah ADB masih kosong.")
        return self._run_plain(
            "adb", "-v", str(index), "-c", command, timeout=timeout
        )

    def get_screen_size(self, index: str) -> tuple[int, int] | None:
        """Ambil resolusi aktif device dari `wm size`."""
        text = self.adb_shell(index, "wm size", timeout=30)
        override = re.findall(r"Override size:\s*(\d+)x(\d+)", text)
        physical = re.findall(r"Physical size:\s*(\d+)x(\d+)", text)
        match = override[-1] if override else (physical[-1] if physical else None)
        if match is None:
            return None
        width, height = int(match[0]), int(match[1])
        if width <= 0 or height <= 0:
            return None
        return width, height

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

    def get_settings_keys(self, index: str, keys: list[str]) -> dict[str, str]:
        """Baca nilai beberapa key setting tanpa memuat seluruh konfigurasi."""
        if not keys:
            return {}
        args = ["setting", "-v", str(index)]
        for key in keys:
            args += ["-k", key]
        data = self._run(*args)
        return {
            str(key): ("" if value is None else str(value))
            for key, value in data.items()
        }

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

    def layout_window(
        self,
        index: str,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> None:
        """Atur posisi dan ukuran jendela player di layar."""
        self._run(
            "control",
            "-v",
            str(index),
            "layout_window",
            "-px",
            str(int(x)),
            "-py",
            str(int(y)),
            "-sw",
            str(max(1, int(width))),
            "-sh",
            str(max(1, int(height))),
        )

    def launch_app(self, index: str, package: str) -> None:
        package = package.strip()
        if not package:
            raise MuMuError("Nama paket aplikasi masih kosong.")
        self._run(
            "control", "-v", str(index), "app", "launch", "--package", package
        )

    def list_installed_apps(self, index: str) -> list[tuple[str, str]]:
        """Daftar (package, label) aplikasi terpasang di device."""
        data = self._run("control", "-v", str(index), "app", "info", "-i")
        return _extract_apps(data)

    def wait_stopped(self, index: str, timeout: int = 45) -> bool:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            info = self.get_info(index)
            if not info.get("is_process_started", False):
                return True
            time.sleep(1.0)
        return False

    def wait_android_started(self, index: str, timeout: int = 120) -> bool:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            info = self.get_info(index)
            if info.get("is_android_started", False):
                return True
            time.sleep(1.0)
        return False

    def launch_device_and_app(
        self, index: str, package: str, timeout: int = 120
    ) -> None:
        package = package.strip()
        if not package:
            raise MuMuError("Nama paket aplikasi masih kosong.")
        self.control(index, "launch")
        self.open_app_when_ready(index, package, timeout)

    def open_app_when_ready(
        self, index: str, package: str, timeout: int = 120, attempts: int = 5
    ) -> None:
        """Buka aplikasi setelah Android siap, dengan beberapa kali percobaan.

        Percobaan ulang diperlukan saat device baru di-restart: Android bisa
        sempat melaporkan siap sebelum benar-benar menerima perintah buka app.
        """
        import time

        package = package.strip()
        if not package:
            raise MuMuError("Nama paket aplikasi masih kosong.")

        deadline = time.monotonic() + timeout
        last_error: Exception | None = None

        for _ in range(max(1, attempts)):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if not self.wait_android_started(index, int(remaining)):
                break
            try:
                self.launch_app(index, package)
                return
            except MuMuError as exc:
                last_error = exc
                time.sleep(3.0)

        detail = f" ({last_error})" if last_error else ""
        raise MuMuError(
            f"Aplikasi {package} belum bisa dibuka dalam {timeout} detik{detail}."
        )
