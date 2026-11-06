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
from app.services.window_layout import DEFAULT_ASPECT, plan_window_rects

ProgressCallback = Callable[[dict], None]
StopCallback = Callable[[], bool]
SleepCallback = Callable[[float], None]
ClockCallback = Callable[[], float]

IDLE_CHECK_SECONDS = 0.5
COUNTDOWN_EVERY_SECONDS = 1.0
APP_CHECK_ATTEMPTS = 3
APP_CHECK_RETRY_SECONDS = 2.0


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


def _device_aspect(client, index: str) -> tuple[float, float]:
    """Rasio resolusi device untuk menghitung ukuran jendela."""
    try:
        getter = getattr(client, "get_settings_keys", None)
        if getter is not None:
            settings = getter(
                index,
                ["resolution_width.custom", "resolution_height.custom"],
            )
        else:
            settings = client.get_settings(index)
    except Exception:  # noqa: BLE001 - pakai rasio default
        return DEFAULT_ASPECT

    try:
        width = float(settings.get("resolution_width.custom", 0) or 0)
        height = float(settings.get("resolution_height.custom", 0) or 0)
    except (AttributeError, TypeError, ValueError):
        return DEFAULT_ASPECT
    if width <= 0 or height <= 0:
        return DEFAULT_ASPECT
    return width, height


def _apply_layout(client, index: str, rect: tuple[int, int, int, int] | None) -> bool:
    if rect is None:
        return False
    layout = getattr(client, "layout_window", None)
    if layout is None:
        return False
    try:
        layout(index, *rect)
    except Exception:  # noqa: BLE001 - penataan bersifat opsional
        return False
    return True


def _installed_packages(
    client,
    index: str,
    sleep: SleepCallback,
    should_stop: StopCallback,
) -> set[str]:
    """Baca paket terpasang dengan beberapa percobaan saat device baru siap."""
    packages: set[str] = set()
    for attempt in range(1, APP_CHECK_ATTEMPTS + 1):
        try:
            packages = {
                package for package, _label in client.list_installed_apps(index)
            }
        except Exception:  # noqa: BLE001 - coba lagi
            packages = set()
        if packages:
            return packages
        if attempt < APP_CHECK_ATTEMPTS:
            _sleep_interruptibly(APP_CHECK_RETRY_SECONDS, sleep, should_stop)
    return packages


def _escape_adb_text(text: str) -> str:
    """Escape teks untuk perintah `input text` di adb shell."""
    # Pada adb shell input text, spasi paling andal dikirim sebagai %s
    # Karakter seperti $ ` " \ perlu di-escape dari shell interpretasi
    escaped = ""
    for char in text:
        if char == " ":
            escaped += "%s"
        elif char in ('"', "'", "\\", "$", "`", "(", ")", "<", ">", "&", ";", "|", "*"):
            escaped += "\\" + char
        else:
            escaped += char
    return f'"{escaped}"'


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
    elif step.action == "text":
        if step.text:
            escaped = _escape_adb_text(step.text)
            client.adb_shell(index, f"input text {escaped}")

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
    window_rect: tuple[int, int, int, int] | None = None,
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
            if _apply_layout(client, index, window_rect):
                _emit(progress, report, "arrange", "Menata jendela device…")
        else:
            _emit(progress, report, "launch", "Device sudah berjalan.")
            _apply_layout(client, index, window_rect)

        _emit(progress, report, "wait", "Menunggu Android siap…")
        if not _wait_android_started(
            client, index, 150, clock, sleep, should_stop
        ):
            report.message = "Android tidak siap dalam 150 detik."
            _emit(progress, report, "error", report.message, "failed")
            return report

        # Ulangi penataan setelah jendela player benar-benar tampil.
        _apply_layout(client, index, window_rect)

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
        installed = _installed_packages(client, index, sleep, should_stop)
        missing = [
            app.package for app in enabled_apps if app.package not in installed
        ]
        if missing:
            report.apps_missing = missing

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
            try:
                client.launch_app(index, app.package)
                report.apps_opened.append(app.package)
            except Exception as exc:  # noqa: BLE001 - jangan gagalkan device, tetap lanjut
                report.script_errors.append(f"Gagal membuka {app.display_name}: {exc}")

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
            remaining = max(0.0, deadline - clock())
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
                    f"Sesi berjalan, sisa {minutes}m {seconds:02d}s",
                    duration=report.duration_sec,
                    remaining_sec=int(remaining),
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
    screen_rect: tuple[int, int, int, int] | None = None,
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
        device_gap_sec=config.device_gap_sec,
        arrange_windows=config.arrange_windows,
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
    cycle = 1
    total_cycles = config.loop_count if config.loop_mode == "count" else (1 if config.loop_mode == "none" else -1)

    while not stop():
        cycle_label = f"Siklus {cycle}" if total_cycles == -1 else (f"Siklus {cycle} dari {total_cycles}" if total_cycles > 1 else "")
        if cycle_label and progress is not None:
            progress(
                {
                    "name": "",
                    "index": "",
                    "batch": 0,
                    "cycle": cycle,
                    "phase": "cycle",
                    "message": f"Memulai {cycle_label}...",
                    "status": "",
                }
            )

        for batch_number, chunk in enumerate(chunks, start=1):
            if stop():
                stopped = True
                break

            if progress is not None:
                batch_msg = f"Memulai batch {batch_number} dari {len(chunks)}"
                if cycle_label:
                    batch_msg += f" ({cycle_label})"
                progress(
                    {
                        "name": "",
                        "index": "",
                        "batch": batch_number,
                        "cycle": cycle,
                        "phase": "batch",
                        "message": f"{batch_msg}.",
                        "status": "",
                    }
                )

            rects: list[tuple[int, int, int, int] | None] = [None] * len(chunk)
            if config.arrange_windows and screen_rect is not None:
                aspects = [
                    _device_aspect(client, index) for index, _name, _device in chunk
                ]
                rects = list(plan_window_rects(aspects, screen_rect))

            gap_sec = max(0, int(config.device_gap_sec))

            def run_one(pos_item):
                position, (index, name, device) = pos_item
                needs_launch = not device.get("is_process_started")
                if needs_launch and position > 0 and gap_sec > 0:
                    total_delay = position * gap_sec
                    gap_deadline = clock_fn() + total_delay
                    while True:
                        if stop():
                            rep = DeviceReport(
                                name=name,
                                index=str(index),
                                batch=batch_number,
                                status="stopped",
                                message="Dihentikan oleh pengguna.",
                                started_at=_now_iso(),
                                finished_at=_now_iso(),
                            )
                            _emit(progress, rep, "stop", rep.message, "stopped")
                            return rep
                        remaining_gap = max(0.0, gap_deadline - clock_fn())
                        if remaining_gap <= 0:
                            break
                        if progress is not None:
                            progress(
                                {
                                    "name": name,
                                    "index": str(index),
                                    "batch": batch_number,
                                    "cycle": cycle,
                                    "phase": "gap",
                                    "message": (
                                        f"Menunggu jeda {int(round(remaining_gap))} detik sebelum "
                                        "menyalakan device…"
                                    ),
                                    "status": "",
                                    "remaining_sec": int(round(remaining_gap)),
                                }
                            )
                        chunk_gap = min(1.0, remaining_gap)
                        sleep_fn(chunk_gap)

                return _run_device_session(
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
                    rects[position],
                )

            with ThreadPoolExecutor(max_workers=max(1, len(chunk))) as pool:
                futures = [pool.submit(run_one, item) for item in enumerate(chunk)]
                for future in futures:
                    report.devices.append(future.result())

            if stop():
                stopped = True
                break

        if stopped or stop():
            stopped = True
            break

        # Cek apakah perlu loop lagi
        has_next_cycle = False
        if config.loop_mode == "infinite":
            has_next_cycle = True
        elif config.loop_mode == "count" and cycle < config.loop_count:
            has_next_cycle = True

        if not has_next_cycle:
            break

        # Jeda antar siklus loop
        cycle_delay = max(0, int(config.loop_delay_sec))
        if cycle_delay > 0:
            loop_deadline = clock_fn() + cycle_delay
            while True:
                if stop():
                    stopped = True
                    break
                remaining_loop = max(0.0, loop_deadline - clock_fn())
                if remaining_loop <= 0:
                    break
                if progress is not None:
                    progress(
                        {
                            "name": "",
                            "index": "",
                            "batch": 0,
                            "cycle": cycle,
                            "phase": "loop_wait",
                            "message": (
                                f"Batch selesai. Menunggu jeda {int(round(remaining_loop))} detik "
                                f"sebelum memulai siklus berikutnya…"
                            ),
                            "status": "",
                            "remaining_sec": int(round(remaining_loop)),
                        }
                    )
                chunk_sleep = min(1.0, remaining_loop)
                sleep_fn(chunk_sleep)

        if stopped or stop():
            stopped = True
            break

        cycle += 1

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
