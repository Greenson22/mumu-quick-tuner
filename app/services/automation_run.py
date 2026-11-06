"""Eksekutor sesi otomatisasi grup."""

from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.services.automation import (
    AutomationConfig,
    AutomationReport,
    DeviceReport,
    KEY_NAMES,
    ScriptStep,
    write_report,
)
from app.services.groups import DeviceRef

ProgressCallback = Callable[[dict], None]
StopCallback = Callable[[], bool]
SleepCallback = Callable[[float], None]
ClockCallback = Callable[[], float]

IDLE_CHECK_SECONDS = 0.5
COUNTDOWN_EVERY_SECONDS = 30.0


class _Stopped(Exception):
    """Sinyal internal saat pengguna menekan Stop."""


def _default_sleep(seconds: float) -> None:
    time.sleep(seconds)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _emit(
    progress: ProgressCallback | None,
    device: DeviceReport,
    phase: str,
    message: str = "",
    status: str = "",
    **extra: object,
) -> None:
    if progress is None:
        return
    payload = {
        "name": device.name,
        "index": device.index,
        "batch": device.batch,
        "phase": phase,
        "message": message,
        "status": status,
        "duration": device.duration_sec,
        "apps_opened": list(device.apps_opened),
    }
    payload.update(extra)
    progress(payload)


def _scale_point(
    x: int,
    y: int,
    screen: tuple[int, int] | None,
    config: AutomationConfig,
) -> tuple[int, int]:
    if not screen or not config.scale_coordinates:
        return x, y
    width, height = screen
    ref_width = max(1, config.reference_width)
    ref_height = max(1, config.reference_height)
    scaled_x = int(round(x * width / ref_width))
    scaled_y = int(round(y * height / ref_height))
    return (
        max(0, min(width - 1, scaled_x)),
        max(0, min(height - 1, scaled_y)),
    )


def _sleep_interruptibly(
    seconds: float, sleep: SleepCallback, should_stop: StopCallback
) -> None:
    remaining = max(0.0, seconds)
    while remaining > 0:
        if should_stop():
            raise _Stopped()
        chunk = min(0.5, remaining)
        sleep(chunk)
        remaining -= chunk


def _wait_android_started(
    client,
    index: str,
    timeout: int,
    clock: ClockCallback,
    sleep: SleepCallback,
    should_stop: StopCallback,
) -> bool:
    deadline = clock() + timeout
    while clock() < deadline:
        if should_stop():
            raise _Stopped()
        try:
            if client.get_info(index).get("is_android_started"):
                return True
        except Exception:  # noqa: BLE001 - coba lagi
            pass
        sleep(min(1.0, max(0.0, deadline - clock())))
    return False


def _run_step(
    client,
    index: str,
    step: ScriptStep,
    config: AutomationConfig,
    screen: tuple[int, int] | None,
    sleep: SleepCallback,
    should_stop: StopCallback,
) -> None:
    if should_stop():
        raise _Stopped()

    if step.action == "wait":
        _sleep_interruptibly(
            max(0, step.delay_ms) / 1000.0, sleep, should_stop
        )
        return

    if step.action == "tap":
        x, y = _scale_point(step.x, step.y, screen, config)
        client.adb_shell(index, f"input tap {x} {y}")
    elif step.action == "swipe":
        x1, y1 = _scale_point(step.x, step.y, screen, config)
        x2, y2 = _scale_point(step.x2, step.y2, screen, config)
        duration = max(50, step.duration_ms)
        client.adb_shell(
            index, f"input swipe {x1} {y1} {x2} {y2} {duration}"
        )
    elif step.action == "key":
        code = KEY_NAMES.get(step.key, KEY_NAMES["back"])
        client.adb_shell(index, f"input keyevent {code}")

    if step.delay_ms > 0:
        _sleep_interruptibly(step.delay_ms / 1000.0, sleep, should_stop)


def _shutdown(client, index: str, wait: bool = True) -> None:
    try:
        client.control(index, "shutdown")
    except Exception:  # noqa: BLE001 - best effort
        return
    if wait:
        try:
            client.wait_stopped(index, 30)
        except Exception:  # noqa: BLE001 - best effort
            pass


def _is_running(client, index: str) -> bool:
    try:
        info = client.get_info(index)
    except Exception:  # noqa: BLE001
        return False
    return bool(info.get("is_process_started"))


def _run_device_session(
    client,
    index: str,
    name: str,
    device: dict,
    batch: int,
    config: AutomationConfig,
    progress: ProgressCallback | None,
    should_stop: StopCallback,
    sleep: SleepCallback,
    clock: ClockCallback,
    rng: random.Random,
) -> DeviceReport:
    report = DeviceReport(
        name=name,
        index=str(index),
        batch=batch,
        status="failed",
        started_at=_now_iso(),
    )

    try:
        if should_stop():
            raise _Stopped()

        if not device.get("is_process_started"):
            _emit(progress, report, "launch", "Menyalakan device…")
            client.control(index, "launch")
        else:
            _emit(progress, report, "launch", "Device sudah berjalan.")

        _emit(progress, report, "wait", "Menunggu Android siap…")
        if not _wait_android_started(
            client, index, 150, clock, sleep, should_stop
        ):
            report.message = "Android tidak siap dalam 150 detik."
            _emit(progress, report, "error", report.message, "failed")
            return report

        if should_stop():
            raise _Stopped()

        report.duration_sec = config.choose_duration(rng)
        _emit(
            progress,
            report,
            "duration",
            f"Durasi sesi {report.duration_sec // 60} menit "
            f"{report.duration_sec % 60} detik.",
        )

        enabled_apps = config.enabled_apps()
        _emit(progress, report, "check", "Memeriksa aplikasi terpasang…")
        installed = {
            package for package, _label in client.list_installed_apps(index)
        }
        missing = [
            app.package for app in enabled_apps if app.package not in installed
        ]
        if missing:
            report.apps_missing = missing
            report.message = (
                "Aplikasi tidak terpasang: " + ", ".join(missing)
                + ". Device dimatikan."
            )
            _emit(progress, report, "error", report.message, "failed")
            report.status = "failed"
            return report

        screen: tuple[int, int] | None = None
        if config.interaction_enabled and config.scale_coordinates:
            try:
                screen = client.get_screen_size(index)
            except Exception:  # noqa: BLE001 - koordinat apa adanya
                screen = None

        session_start = clock()
        app_count = len(enabled_apps)
        for position, app in enumerate(enabled_apps, start=1):
            if should_stop():
                raise _Stopped()

            _emit(
                progress,
                report,
                "app",
                f"Membuka {app.display_name} ({position}/{app_count})…",
            )
            client.launch_app(index, app.package)
            report.apps_opened.append(app.package)

            if not config.interaction_enabled or not app.steps:
                continue

            # Beri waktu UI aplikasi muncul sebelum langkah pertama.
            _sleep_interruptibly(2.0, sleep, should_stop)

            for step_number, step in enumerate(app.steps, start=1):
                if should_stop():
                    raise _Stopped()
                _emit(
                    progress,
                    report,
                    "script",
                    f"{app.display_name}: langkah {step_number}/"
                    f"{len(app.steps)} — {step.describe()}",
                )
                try:
                    _run_step(
                        client,
                        index,
                        step,
                        config,
                        screen,
                        sleep,
                        should_stop,
                    )
                except _Stopped:
                    raise
                except Exception as exc:  # noqa: BLE001 - lanjut langkah lain
                    report.script_errors.append(
                        f"{app.display_name} langkah {step_number}: {exc}"
                    )

        deadline = session_start + report.duration_sec
        last_countdown = -COUNTDOWN_EVERY_SECONDS
        while True:
            if should_stop():
                raise _Stopped()
            remaining = deadline - clock()
            if remaining <= 0:
                break
            elapsed = report.duration_sec - remaining
            if elapsed - last_countdown >= COUNTDOWN_EVERY_SECONDS:
                last_countdown = elapsed
                minutes = int(remaining) // 60
                seconds = int(remaining) % 60
                _emit(
                    progress,
                    report,
                    "session",
                    f"Sesi berjalan, sisa {minutes} menit {seconds} detik.",
                    duration=report.duration_sec,
                )
            sleep(min(IDLE_CHECK_SECONDS, remaining))

        report.status = "success"
        report.message = f"Sesi selesai ({report.duration_sec} detik)."

    except _Stopped:
        report.status = "stopped"
        report.message = "Dihentikan oleh pengguna."
        _emit(progress, report, "stop", report.message, "stopped")
    except Exception as exc:  # noqa: BLE001 - dilaporkan per device
        report.status = "failed"
        report.message = str(exc)
        _emit(progress, report, "error", report.message, "failed")
    finally:
        report.finished_at = _now_iso()
        if report.status == "stopped":
            _shutdown(client, index)
        elif report.status == "failed":
            _shutdown(client, index)
        elif report.status == "success":
            _emit(progress, report, "shutdown", "Mematikan device…")
            _shutdown(client, index)
            _emit(progress, report, "done", report.message, "success")

    return report


def _final_shutdown(client, targets: list[tuple[str, str, dict]]) -> None:
    """Pastikan semua device yang terlibat benar-benar mati."""
    if not targets:
        return

    def stop_one(index: str) -> None:
        if not _is_running(client, index):
            return
        try:
            client.control(index, "shutdown")
            client.wait_stopped(index, 30)
        except Exception:  # noqa: BLE001
            pass

    with ThreadPoolExecutor(max_workers=max(1, len(targets))) as pool:
        list(pool.map(stop_one, [index for index, _name, _device in targets]))


def run_automation(
    client,
    group_name: str,
    targets: list[tuple[str, str, dict]],
    missing: list[DeviceRef],
    config: AutomationConfig,
    report_dir: Path,
    progress: ProgressCallback | None = None,
    should_stop: StopCallback | None = None,
    sleep: SleepCallback | None = None,
    clock: ClockCallback | None = None,
    rng: random.Random | None = None,
) -> AutomationReport:
    """Jalankan sesi otomatisasi untuk seluruh anggota grup.

    Args:
        client: objek dengan API MuMuClient (bisa fake untuk tes).
        group_name: nama grup untuk laporan.
        targets: [(index, name, device_dict), ...] hasil GroupStore.resolve.
        missing: anggota grup yang tidak ditemukan.
        config: konfigurasi otomatisasi.
        report_dir: folder tujuan laporan JSON.
    """
    stop = should_stop or (lambda: False)
    sleep_fn = sleep or _default_sleep
    clock_fn = clock or time.monotonic
    generator = rng or random.Random()
    batch_size = max(1, config.batch_size)

    report = AutomationReport(
        group=group_name,
        batch_size=batch_size,
        duration_min_sec=config.duration_min_sec,
        duration_max_sec=config.duration_max_sec,
        interaction_enabled=config.interaction_enabled,
        started_at=_now_iso(),
    )

    for ref in missing:
        report.devices.append(
            DeviceReport(
                name=ref.name,
                index=str(ref.index or "?"),
                status="skipped",
                message="Device tidak ditemukan.",
                started_at=_now_iso(),
                finished_at=_now_iso(),
            )
        )

    chunks = [
        targets[offset : offset + batch_size]
        for offset in range(0, len(targets), batch_size)
    ]

    stopped = False
    for batch_number, chunk in enumerate(chunks, start=1):
        if stop():
            stopped = True
            break

        if progress is not None:
            progress(
                {
                    "name": "",
                    "index": "",
                    "batch": batch_number,
                    "phase": "batch",
                    "message": f"Memulai batch {batch_number} dari {len(chunks)}.",
                    "status": "",
                }
            )

        with ThreadPoolExecutor(max_workers=max(1, len(chunk))) as pool:
            futures = [
                pool.submit(
                    _run_device_session,
                    client,
                    index,
                    name,
                    device,
                    batch_number,
                    config,
                    progress,
                    stop,
                    sleep_fn,
                    clock_fn,
                    generator,
                )
                for index, name, device in chunk
            ]
            for future in futures:
                report.devices.append(future.result())

        if stop():
            stopped = True
            break

    if stopped:
        report.stopped_by_user = True
        processed = {device.name for device in report.devices}
        for index, name, _device in targets:
            if name in processed:
                continue
            report.devices.append(
                DeviceReport(
                    name=name,
                    index=str(index),
                    status="skipped",
                    message="Dibatalkan karena otomatisasi dihentikan.",
                    started_at=_now_iso(),
                    finished_at=_now_iso(),
                )
            )
    elif stop():
        report.stopped_by_user = True

    _final_shutdown(client, targets)
    report.finished_at = _now_iso()
    write_report(report, report_dir)
    return report
