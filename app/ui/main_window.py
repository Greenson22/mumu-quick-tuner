"""Jendela utama aplikasi."""

from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import models
from app.config import AppConfig
from app.mumu import MuMuClient, MuMuError, pick_device
from app.services.backup import create_backup, resolve_vm_dir
from app.services.group_apply import BatchResult, run_batch
from app.services.groups import GroupStore
from app.services.profiles import ProfileStore
from app.ui.groups import GroupsSection
from app.ui.sections import (
    GrafisSection,
    PerformaSection,
    ProfilesSection,
    TampilanSection,
)

logger = logging.getLogger(__name__)


class Worker(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:  # pragma: no cover - dijalankan di thread
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001 - diteruskan ke UI
            logger.exception("Worker gagal")
            self.failed.emit(str(exc))
            return
        self.done.emit(result)


class MainWindow(QMainWindow):
    groupProgress = pyqtSignal(object)

    def __init__(self, config: AppConfig, client: MuMuClient) -> None:
        super().__init__()
        self.config = config
        self.client = client
        self.store = ProfileStore()
        self.group_store = GroupStore()

        self.index: str | None = None
        self.device: dict = {}
        self.info: dict = {}
        self.settings: dict[str, str] = {}
        self.devices: dict[str, dict] = {}
        self._busy = False
        self._workers: list[Worker] = []
        self._last_failed: list[tuple[str, str]] = []
        self._last_batch: tuple[str, str, dict[str, str], bool] | None = None

        self.setWindowTitle("MuMu Quick Tuner")
        self.resize(960, 780)
        self._build_ui()

        QTimer.singleShot(50, self.refresh)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)

        # judul
        title_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("MuMu Quick Tuner")
        title.setObjectName("appTitle")
        subtitle = QLabel("Atur resolusi, FPS, renderer, dan performa dalam satu klik.")
        subtitle.setObjectName("appSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        title_row.addLayout(title_box)
        title_row.addStretch(1)

        self.refresh_button = QPushButton("Muat Ulang")
        self.refresh_button.clicked.connect(self.refresh)
        title_row.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(title_row)

        # kartu device
        device_card = QFrame()
        device_card.setObjectName("card")
        device_layout = QHBoxLayout(device_card)
        device_layout.setContentsMargins(18, 14, 18, 14)
        device_layout.setSpacing(12)

        device_text = QVBoxLayout()
        device_text.setSpacing(3)
        self.device_name = QLabel("Memuat device…")
        self.device_name.setObjectName("deviceName")
        self.device_meta = QLabel("Menghubungkan ke MuMuManager…")
        self.device_meta.setObjectName("hint")
        device_text.addWidget(self.device_name)
        device_text.addWidget(self.device_meta)
        device_layout.addLayout(device_text)
        device_layout.addStretch(1)

        self.badge = QLabel("Memuat")
        self.badge.setObjectName("badge")
        self.badge.setProperty("state", "off")
        device_layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(device_card)

        # tab
        self.tabs = QTabWidget()
        self.tampilan = TampilanSection()
        self.grafis = GrafisSection()
        self.performa = PerformaSection()
        self.profiles = ProfilesSection(self.store)
        self.groups = GroupsSection(self.store, self.group_store)

        self.tabs.addTab(self.tampilan, "Tampilan")
        self.tabs.addTab(self.grafis, "Grafis")
        self.tabs.addTab(self.performa, "Performa")
        self.tabs.addTab(self.profiles, "Profil")
        self.tabs.addTab(self.groups, "Grup")
        layout.addWidget(self.tabs, 1)

        self.profiles.loadRequested.connect(self._load_profile_into_form)
        self.profiles.applyRequested.connect(self._apply_profile)
        self.profiles.saveRequested.connect(self._save_profile)
        self.profiles.deleteRequested.connect(self._delete_profile)

        self.groups.refreshRequested.connect(self.refresh)
        self.groups.applyRequested.connect(self._on_group_apply)
        self.groups.copyCurrentRequested.connect(self._on_group_copy_current)
        self.groups.savePresetRequested.connect(self._save_preset_from_current)
        self.groups.retryRequested.connect(self._retry_failed)
        self.groupProgress.connect(self.groups.update_progress)

        # action bar
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.status_label = QLabel("Siap.")
        self.status_label.setObjectName("hint")
        actions.addWidget(self.status_label)
        actions.addStretch(1)

        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self.refresh)
        self.restart_button = QPushButton("Restart Device")
        self.restart_button.clicked.connect(self._restart_device)
        self.apply_button = QPushButton("Terapkan")
        self.apply_button.setObjectName("primary")
        self.apply_button.clicked.connect(self._apply_changes)

        actions.addWidget(self.reset_button)
        actions.addWidget(self.restart_button)
        actions.addWidget(self.apply_button)
        layout.addLayout(actions)

        self.statusBar().showMessage("Siap.")

    # ------------------------------------------------------------- helpers
    def _run_async(self, fn, on_done, on_error=None) -> None:
        worker = Worker(fn, self)
        self._workers.append(worker)
        worker.done.connect(on_done)
        worker.failed.connect(on_error or self._on_error)
        worker.finished.connect(lambda: self._release_worker(worker))
        worker.start()

    def _release_worker(self, worker: Worker) -> None:
        try:
            self._workers.remove(worker)
        except ValueError:
            pass
        worker.deleteLater()

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        for widget in (
            self.apply_button,
            self.restart_button,
            self.reset_button,
            self.refresh_button,
            self.tabs,
        ):
            widget.setEnabled(not busy)
        if message:
            self.status_label.setText(message)
            self.statusBar().showMessage(message)
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    def _on_error(self, message: str) -> None:
        self._set_busy(False, "Gagal.")
        QMessageBox.critical(self, "Gagal", message)
        self.statusBar().showMessage("Gagal: " + message.splitlines()[0])

    # ------------------------------------------------------------- refresh
    def refresh(self) -> None:
        if self._busy:
            return
        self._set_busy(True, "Membaca konfigurasi device…")

        def work():
            devices = self.client.list_devices()
            try:
                index, device = pick_device(
                    devices, self.config.vm_name, self.config.vm_index
                )
            except MuMuError as exc:
                return devices, None, {}, {}, {}, str(exc)
            info = self.client.get_info(index)
            settings = self.client.get_settings(index)
            return devices, index, device, info, settings, ""

        self._run_async(work, self._on_loaded)

    def _on_loaded(self, payload) -> None:
        devices, index, device, info, settings, active_error = payload
        self.devices = devices

        if index is None:
            self.index = None
            self.device = {}
            self.info = {}
            self.settings = {}
            self.device_name.setText("Tidak ada device aktif")
            self.device_meta.setText(active_error or "Pilih device lewat .env.")
            self.badge.setText("Tidak aktif")
            self.badge.setProperty("state", "warn")
            self.badge.style().unpolish(self.badge)
            self.badge.style().polish(self.badge)
        else:
            self.index = index
            self.device = device
            self.info = info
            self.settings = settings
            self._update_header()
            for section in (self.tampilan, self.grafis, self.performa):
                section.load(settings)

        self.profiles.reload()
        self.groups.set_devices(devices)
        self.groups.reload_presets()

        self._set_busy(False, "Konfigurasi dimuat.")
        if index is None:
            self.statusBar().showMessage(
                f"{len(devices)} device terdeteksi, tetapi device aktif tidak ditemukan."
            )
        else:
            self.statusBar().showMessage(
                f"{len(devices)} device terdeteksi. Device "
                f"{device.get('name', index)} siap diatur."
            )

    def _update_header(self) -> None:
        name = self.device.get("name") or self.config.vm_name or "Device"
        self.device_name.setText(name)

        running = bool(self.info.get("is_process_started"))
        android = self.info.get("android_version", "?")
        self.device_meta.setText(
            f"Index {self.index}  •  Android {android}  •  "
            f"{'Sedang berjalan' if running else 'Berhenti'}"
        )

        self.badge.setText("Berjalan" if running else "Berhenti")
        self.badge.setProperty("state", "ok" if running else "off")
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)

    # ---------------------------------------------------------- form utils
    def _collect_all(self) -> dict[str, str]:
        data: dict[str, str] = {}
        for section in (self.tampilan, self.grafis, self.performa):
            data.update(section.collect())
        return data

    def _pending_changes(self) -> dict[str, str]:
        current = self._collect_all()
        changes: dict[str, str] = {}
        for key, value in current.items():
            if str(value) != str(self.settings.get(key, "")):
                changes[key] = str(value)
        return changes

    def _load_profile_into_form(self, changes: dict[str, str]) -> None:
        merged = dict(self.settings)
        merged.update(changes)
        for section in (self.tampilan, self.grafis, self.performa):
            section.load(merged)
        self.status_label.setText("Profil dimuat ke form. Tekan Terapkan.")
        self.statusBar().showMessage("Profil dimuat ke form.")

    def _apply_profile(self, changes: dict[str, str]) -> None:
        self._load_profile_into_form(changes)
        self._apply_changes()

    # --------------------------------------------------------------- group
    def _on_group_apply(self, group: str, preset_name: str, relaunch: bool) -> None:
        if self._busy:
            return
        preset = self.store.get(preset_name)
        if preset is None:
            QMessageBox.warning(
                self, "Preset tidak ditemukan", f"Preset '{preset_name}' tidak ada."
            )
            return
        if not self.devices:
            QMessageBox.warning(
                self, "Belum ada data device", "Muat ulang daftar device dulu."
            )
            return

        found, missing = self.group_store.resolve(group, self.devices)
        if not found:
            QMessageBox.warning(
                self,
                "Grup kosong",
                f"Tidak ada device dari grup '{group}' yang terdeteksi.",
            )
            return

        if not self._confirm_group_shutdown(found, f"preset '{preset_name}'"):
            return

        targets = [(name, index) for index, name, _device in found]
        self._start_batch(group, preset_name, dict(preset), targets, missing, relaunch)

    def _on_group_copy_current(self, group: str) -> None:
        if self._busy:
            return
        if self.index is None or not self.settings:
            QMessageBox.warning(
                self,
                "Device aktif belum siap",
                "Muat ulang data device aktif terlebih dahulu.",
            )
            return

        preset = models.filter_managed(self._collect_all())
        if not preset:
            QMessageBox.warning(
                self, "Tidak ada setting", "Form device aktif tidak berisi setting."
            )
            return

        found, missing = self.group_store.resolve(group, self.devices)
        if not found:
            QMessageBox.warning(
                self,
                "Grup kosong",
                f"Tidak ada device dari grup '{group}' yang terdeteksi.",
            )
            return

        if not self._confirm_group_shutdown(found, "setting device aktif"):
            return

        targets = [(name, index) for index, name, _device in found]
        self._start_batch(
            group,
            "Device aktif",
            preset,
            targets,
            missing,
            self.groups.relaunch_check.isChecked(),
        )

    def _confirm_group_shutdown(
        self, found: list[tuple[str, str, dict]], action: str
    ) -> bool:
        running = [
            (index, name)
            for index, name, device in found
            if device.get("is_process_started")
        ]
        if not running:
            return True

        names = "\n".join(f"• {name}  (index {index})" for index, name in running)
        relaunch_note = (
            "Device akan dinyalakan kembali otomatis setelah selesai."
            if self.groups.relaunch_check.isChecked()
            else "Device TIDAK akan dinyalakan kembali otomatis."
        )

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Device sedang berjalan")
        box.setText(
            f"Akan menerapkan {action} ke grup.\n\n"
            "MuMu hanya menerima perubahan setting saat device berhenti. "
            f"Device berikut akan dimatikan lebih dulu:\n\n{names}\n\n"
            f"{relaunch_note}\n\nLanjutkan?"
        )
        proceed = box.addButton("Matikan && Terapkan", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Batal", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is proceed

    def _start_batch(
        self,
        group: str,
        preset_name: str,
        preset: dict[str, str],
        targets: list[tuple[str, str]],
        missing: list,
        relaunch: bool,
    ) -> None:
        if not targets and not missing:
            QMessageBox.information(
                self, "Tidak ada device", "Grup ini belum memiliki anggota."
            )
            return

        preset = models.filter_managed(preset)
        self._last_batch = (group, preset_name, dict(preset), relaunch)
        self._last_failed = []

        rows = list(targets) + [
            (ref.name, ref.index or "?") for ref in missing
        ]
        self.groups.start_progress(rows)
        self._set_busy(
            True, f"Menerapkan '{preset_name}' ke grup '{group}'…"
        )

        def emit(payload: dict) -> None:
            self.groupProgress.emit(payload)

        def work():
            devices = self.client.list_devices()
            by_name = {
                str(device.get("name", "")).strip(): (str(index), device)
                for index, device in devices.items()
            }

            resolved: list[tuple[str, str, dict]] = []
            failures: list[BatchResult] = []
            seen: set[str] = set()

            for name, fallback_index in list(targets) + [
                (ref.name, ref.index or "?") for ref in missing
            ]:
                if name in seen:
                    continue
                seen.add(name)
                match = by_name.get(name)
                if match is None:
                    failures.append(
                        BatchResult(
                            name, str(fallback_index), "failed",
                            "Device tidak ditemukan.",
                        )
                    )
                    emit(
                        {
                            "name": name,
                            "index": str(fallback_index),
                            "phase": "error",
                            "message": "Device tidak ditemukan.",
                            "status": "failed",
                        }
                    )
                    continue
                index, device = match
                resolved.append((name, index, device))

            stopped: list[tuple[str, str]] = []
            shutdown_failed: set[str] = set()
            for name, index, device in resolved:
                if not device.get("is_process_started"):
                    continue
                emit(
                    {
                        "name": name,
                        "index": index,
                        "phase": "shutdown",
                        "message": "Mematikan device…",
                        "status": "",
                    }
                )
                try:
                    self.client.control(index, "shutdown")
                    if not self.client.wait_stopped(index, 45):
                        raise MuMuError(
                            "Device tidak berhenti dalam 45 detik."
                        )
                    stopped.append((name, index))
                except Exception as exc:  # noqa: BLE001 - lanjut device lain
                    shutdown_failed.add(name)
                    failures.append(
                        BatchResult(
                            name, index, "failed",
                            f"Gagal mematikan device: {exc}",
                        )
                    )
                    emit(
                        {
                            "name": name,
                            "index": index,
                            "phase": "error",
                            "message": f"Gagal mematikan: {exc}",
                            "status": "failed",
                        }
                    )

            valid = [
                (name, index)
                for name, index, _device in resolved
                if name not in shutdown_failed
            ]
            results = run_batch(
                self.client,
                valid,
                preset,
                self.config.backup_dir,
                progress=emit,
            )
            results.extend(failures)

            if relaunch:
                for name, index in stopped:
                    emit(
                        {
                            "name": name,
                            "index": index,
                            "phase": "launch",
                            "message": "Menyalakan kembali device…",
                            "status": "",
                        }
                    )
                    try:
                        self.client.control(index, "launch")
                    except Exception as exc:  # noqa: BLE001
                        results.append(
                            BatchResult(
                                name, index, "failed",
                                f"Setting selesai, tetapi gagal menyalakan: {exc}",
                            )
                        )
                        emit(
                            {
                                "name": name,
                                "index": index,
                                "phase": "error",
                                "message": f"Gagal menyalakan: {exc}",
                                "status": "failed",
                            }
                        )

            return results, [name for name, _index in stopped]

        self._run_async(
            work,
            lambda payload: self._on_group_batch_done(payload),
        )

    def _on_group_batch_done(self, payload) -> None:
        results, relaunched = payload
        results = list(results)
        self._set_busy(False, "Batch selesai.")

        group, preset_name, _preset, _relaunch = self._last_batch or (
            "-", "-", {}, False
        )
        if self.store.get(preset_name) is not None:
            self.group_store.set_last_preset(group, preset_name)

        self._last_failed = [
            (result.name, result.index)
            for result in results
            if result.status == "failed"
        ]
        self.groups.set_retry_enabled(bool(self._last_failed))

        success = sum(1 for result in results if result.status == "success")
        unchanged = sum(1 for result in results if result.status == "unchanged")
        failed = [result for result in results if result.status == "failed"]

        message = (
            f"Preset '{preset_name}' diterapkan ke grup '{group}'.\n\n"
            f"Berhasil diubah: {success}\n"
            f"Tidak berubah: {unchanged}\n"
            f"Gagal: {len(failed)}"
        )
        if failed:
            lines = "\n".join(
                f"• {result.name}: {result.message}" for result in failed[:10]
            )
            if len(failed) > 10:
                lines += f"\n… dan {len(failed) - 10} device lain."
            message += "\n\nDevice gagal:\n" + lines
            message += "\n\nGunakan tombol 'Ulangi yang Gagal' di tab Grup."
        if relaunched:
            message += f"\n\n{len(relaunched)} device berjalan dinyalakan kembali."

        QMessageBox.information(self, "Batch selesai", message)
        self.refresh()

    def _retry_failed(self) -> None:
        if self._busy or not self._last_failed:
            return
        if self._last_batch is None:
            return
        group, preset_name, preset, relaunch = self._last_batch
        self._start_batch(
            group, preset_name, preset, list(self._last_failed), [], relaunch
        )

    def _save_preset_from_current(self) -> None:
        if self.index is None or not self.settings:
            QMessageBox.warning(
                self,
                "Device aktif belum siap",
                "Muat ulang data device aktif terlebih dahulu.",
            )
            return

        name, ok = QInputDialog.getText(
            self, "Simpan Preset", "Nama preset baru:"
        )
        name = name.strip()
        if not ok or not name:
            return

        builtin_names = {
            item[0] for item in self.store.all_profiles() if item[2]
        }
        if name in builtin_names:
            QMessageBox.warning(
                self,
                "Nama terpakai",
                "Nama tersebut dipakai preset bawaan. Gunakan nama lain.",
            )
            return

        if name in self.store.load_custom():
            if (
                QMessageBox.question(
                    self, "Timpa preset", f"Preset '{name}' sudah ada. Timpa?"
                )
                != QMessageBox.StandardButton.Yes
            ):
                return

        changes = models.filter_managed(self._collect_all())
        self.store.save_custom(name, changes)
        self.profiles.reload()
        self.groups.reload_presets()
        index = self.groups.preset_combo.findData(name)
        if index >= 0:
            self.groups.preset_combo.setCurrentIndex(index)
        self.statusBar().showMessage(f"Preset '{name}' disimpan.")

    # --------------------------------------------------------------- apply
    def _apply_changes(self) -> None:
        if self._busy:
            return
        if self.index is None:
            QMessageBox.warning(self, "Device belum siap", "Muat ulang data device dulu.")
            return

        changes = self._pending_changes()
        if not changes:
            QMessageBox.information(
                self, "Tidak ada perubahan", "Semua nilai sama dengan device."
            )
            return

        if not self._ensure_writable():
            return

        restart_keys = [key for key in changes if key in models.RESTART_KEYS]
        running = bool(self.info.get("is_process_started"))
        shutdown_first = False

        if running:
            details = "\n".join(
                f"• {models.LABELS.get(key, key)}" for key in changes
            )
            note = ""
            if restart_keys:
                note = (
                    "\n\nSebagian perubahan (" +
                    ", ".join(models.LABELS.get(k, k) for k in restart_keys) +
                    ") juga memerlukan restart."
                )
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Device sedang berjalan")
            box.setText(
                "MuMu hanya menerima perubahan setting saat device berhenti.\n\n"
                f"Perubahan yang menunggu:\n{details}{note}\n\n"
                "Matikan device sekarang lalu terapkan?"
            )
            stop_button = box.addButton(
                "Matikan && Terapkan", QMessageBox.ButtonRole.AcceptRole
            )
            box.addButton("Batal", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is not stop_button:
                return
            shutdown_first = True

        old_settings = dict(self.settings)
        backup = create_backup(self.settings, self.config.backup_dir)
        if backup:
            self.statusBar().showMessage(f"Backup dibuat: {backup}")

        hint = "Mematikan device dan menerapkan…" if shutdown_first else "Menerapkan…"
        self._set_busy(True, hint)

        def work():
            if shutdown_first:
                self.client.control(self.index, "shutdown")
                if not self.client.wait_stopped(self.index, 45):
                    raise MuMuError(
                        "Device tidak berhenti dalam 45 detik. "
                        "Tutup device secara manual lalu coba lagi."
                    )
            self.client.apply(self.index, changes)
            return self.client.get_settings(self.index)

        self._run_async(
            work,
            lambda new_settings: self._on_applied(
                new_settings, changes, old_settings, shutdown_first
            ),
        )

    def _on_applied(
        self,
        new_settings: dict[str, str],
        changes: dict[str, str],
        old_settings: dict[str, str],
        stopped_for_apply: bool = False,
    ) -> None:
        self.settings = new_settings
        for section in (self.tampilan, self.grafis, self.performa):
            section.load(new_settings)

        lines = [
            models.describe_change(key, old_settings.get(key, "-"), value)
            for key, value in changes.items()
        ]

        self._set_busy(False, "Perubahan diterapkan.")
        message = "Setting berikut sudah diterapkan:\n\n" + "\n".join(
            f"• {x}" for x in lines
        )
        if stopped_for_apply:
            message += (
                "\n\nDevice dalam keadaan mati. Gunakan tombol "
                "Restart Device untuk menyalakannya."
            )
        QMessageBox.information(self, "Berhasil", message)

        self.refresh()

    # ------------------------------------------------------------- restart
    def _restart_device(self) -> None:
        if self._busy or self.index is None:
            return

        running = bool(self.info.get("is_process_started"))
        action = "restart" if running else "launch"
        question = (
            "Restart device sekarang?" if running else "Nyalakan device sekarang?"
        )
        if (
            QMessageBox.question(self, "Konfirmasi", question)
            != QMessageBox.StandardButton.Yes
        ):
            return

        self._set_busy(True, "Memproses device…")

        def work():
            self.client.control(self.index, action)
            return True

        def done(_):
            self._set_busy(False, "Perintah dikirim.")
            QTimer.singleShot(2500, self.refresh)

        self._run_async(work, done)

    # ------------------------------------------------------------- profile
    def _save_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "Simpan Profil", "Nama profil:")
        name = name.strip()
        if not ok or not name:
            return

        builtin_names = {
            item[0] for item in self.store.all_profiles() if item[2]
        }
        if name in builtin_names:
            QMessageBox.warning(
                self,
                "Nama terpakai",
                "Nama tersebut dipakai preset bawaan. Gunakan nama lain.",
            )
            return

        if name in self.store.load_custom():
            if (
                QMessageBox.question(
                    self, "Timpa profil", f"Profil '{name}' sudah ada. Timpa?"
                )
                != QMessageBox.StandardButton.Yes
            ):
                return

        self.store.save_custom(name, self._collect_all())
        self.profiles.reload()
        self.groups.reload_presets()
        self.statusBar().showMessage(f"Profil '{name}' disimpan.")

    def _delete_profile(self, name: str) -> None:
        if (
            QMessageBox.question(self, "Hapus profil", f"Hapus profil '{name}'?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.store.delete_custom(name)
        self.profiles.reload()
        self.groups.reload_presets()

    # --------------------------------------------------------------- admin
    def _ensure_writable(self) -> bool:
        vm_dir = resolve_vm_dir(self.settings)
        if vm_dir is None or not vm_dir.is_dir():
            return True

        probe = vm_dir / ".mumu_tuner_write_test"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return True
        except OSError:
            answer = QMessageBox.question(
                self,
                "Butuh izin Administrator",
                "Aplikasi tidak dapat menulis ke folder MuMu "
                f"({vm_dir}).\n\nJalankan ulang sebagai Administrator?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._relaunch_as_admin()
            return False

    def _relaunch_as_admin(self) -> None:
        if sys.platform != "win32":
            return
        params = "-m app.main"
        try:
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params,
                str(self.config.project_root), 1,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Gagal", f"Tidak bisa elevation: {exc}")
            return

        if result <= 32:
            QMessageBox.critical(
                self, "Gagal", "Permintaan Administrator ditolak atau gagal."
            )
        else:
            QApplication.quit()

    # --------------------------------------------------------------- close
    def closeEvent(self, event: QCloseEvent) -> None:
        for worker in list(self._workers):
            worker.wait(100)
        super().closeEvent(event)
