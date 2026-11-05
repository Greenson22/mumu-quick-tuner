"""Tab Grup: deteksi device, kelola grup, dan terapkan preset."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from app.services.groups import DeviceRef, GroupStore
from app.services.profiles import ProfileStore
from app.ui.sections import ScrollSection
from app.ui.widgets import Card, checkbox

PHASE_LABELS = {
    "wait": "Menunggu",
    "shutdown": "Mematikan device",
    "read": "Membaca setting",
    "backup": "Backup",
    "apply": "Menerapkan",
    "verify": "Verifikasi",
    "done": "Selesai",
    "unchanged": "Tidak berubah",
    "error": "Gagal",
    "skip": "Dilewati",
    "launch": "Menyalakan device",
}


class GroupsSection(ScrollSection):
    refreshRequested = pyqtSignal()
    applyRequested = pyqtSignal(str, str, bool)  # group, preset, relaunch
    copyCurrentRequested = pyqtSignal(str)  # group
    savePresetRequested = pyqtSignal()
    retryRequested = pyqtSignal()

    def __init__(
        self,
        profile_store: ProfileStore,
        group_store: GroupStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.profile_store = profile_store
        self.group_store = group_store or GroupStore()
        self.devices: dict[str, dict] = {}
        self._progress_rows: dict[str, int] = {}
        self._retry_available = False

        self._build_devices_card()
        self._build_groups_card()
        self._build_apply_card()
        self._build_progress_card()
        self._sync_buttons()

    # ------------------------------------------------------------------ UI
    def _build_devices_card(self) -> None:
        card = Card(
            "Device terdeteksi",
            "Centang device yang ingin dimasukkan ke grup. Nama device tidak "
            "diubah oleh aplikasi ini.",
        )

        self.device_table = QTableWidget(0, 6)
        self.device_table.setHorizontalHeaderLabels(
            ["", "Nama device", "Index", "Android", "Status", "Grup"]
        )
        self.device_table.verticalHeader().setVisible(False)
        self.device_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.device_table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.device_table.setAlternatingRowColors(True)
        self.device_table.setMinimumHeight(230)

        header = self.device_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (2, 3, 4):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        card.form.addRow(self.device_table)

        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("Muat Ulang")
        self.select_all_button = QPushButton("Pilih Semua")
        self.clear_button = QPushButton("Kosongkan")
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.select_all_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        card.form.addRow(buttons)

        self.add_card(card)

        self.refresh_button.clicked.connect(self.refreshRequested.emit)
        self.select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        self.clear_button.clicked.connect(lambda: self._set_all_checked(False))

    def _build_groups_card(self) -> None:
        card = Card(
            "Grup tersimpan",
            "Pilih device di tabel atas, lalu buat grup. Anggota grup disimpan "
            "berdasarkan nama device.",
        )

        self.group_list = QListWidget()
        self.group_list.setMinimumHeight(150)
        card.form.addRow(self.group_list)

        buttons = QHBoxLayout()
        self.create_group_button = QPushButton("Buat Grup…")
        self.create_group_button.setObjectName("primary")
        self.add_button = QPushButton("Tambah Pilihan")
        self.remove_button = QPushButton("Keluarkan Pilihan")
        self.rename_group_button = QPushButton("Ganti Nama…")
        self.delete_group_button = QPushButton("Hapus")
        self.delete_group_button.setObjectName("danger")

        for button in (
            self.create_group_button,
            self.add_button,
            self.remove_button,
            self.rename_group_button,
            self.delete_group_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        card.form.addRow(buttons)

        self.add_card(card)

        self.group_list.itemSelectionChanged.connect(self._sync_buttons)
        self.create_group_button.clicked.connect(self._create_group)
        self.add_button.clicked.connect(self._add_to_group)
        self.remove_button.clicked.connect(self._remove_from_group)
        self.rename_group_button.clicked.connect(self._rename_group)
        self.delete_group_button.clicked.connect(self._delete_group)

    def _build_apply_card(self) -> None:
        card = Card(
            "Terapkan ke grup",
            "Semua device di grup akan memakai setting yang sama. Device yang "
            "sedang berjalan akan dimatikan lebih dulu, lalu bisa dinyalakan lagi.",
        )

        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(360)
        card.add_row("Preset setting", self.preset_combo)

        self.relaunch_check = checkbox(
            "Nyalakan kembali device yang tadi berjalan"
        )
        self.relaunch_check.setChecked(True)
        card.add_row("Setelah selesai", self.relaunch_check)

        buttons = QHBoxLayout()
        self.apply_button = QPushButton("Terapkan ke Grup")
        self.apply_button.setObjectName("primary")
        self.copy_button = QPushButton("Samakan dengan Device Aktif")
        self.save_preset_button = QPushButton("Simpan Setting Aktif sebagai Preset…")
        self.retry_button = QPushButton("Ulangi yang Gagal")

        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.save_preset_button)
        buttons.addStretch(1)
        buttons.addWidget(self.retry_button)
        card.form.addRow(buttons)

        self.add_card(card)

        self.preset_combo.currentIndexChanged.connect(self._sync_buttons)
        self.apply_button.clicked.connect(self._request_apply)
        self.copy_button.clicked.connect(self._request_copy)
        self.save_preset_button.clicked.connect(self.savePresetRequested.emit)
        self.retry_button.clicked.connect(self.retryRequested.emit)

    def _build_progress_card(self) -> None:
        card = Card(
            "Progres terakhir",
            "Status per device saat preset diterapkan.",
        )

        self.progress_table = QTableWidget(0, 3)
        self.progress_table.setHorizontalHeaderLabels(
            ["Device", "Tahap", "Keterangan"]
        )
        self.progress_table.verticalHeader().setVisible(False)
        self.progress_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.progress_table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.progress_table.setAlternatingRowColors(True)
        self.progress_table.setMinimumHeight(170)

        header = self.progress_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        card.form.addRow(self.progress_table)
        self.add_card(card)

    # -------------------------------------------------------------- public
    def set_devices(self, devices: dict[str, dict]) -> None:
        checked = {ref.name for ref in self.checked_device_refs()}
        self.devices = dict(devices)
        self.device_table.setRowCount(0)

        members = self._membership_map()

        for index, device in sorted(
            self.devices.items(), key=lambda item: int(item[0])
        ):
            name = str(device.get("name", "")).strip()
            if not name:
                continue
            row = self.device_table.rowCount()
            self.device_table.insertRow(row)

            check = QTableWidgetItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
            )
            check.setCheckState(
                Qt.CheckState.Checked
                if name in checked
                else Qt.CheckState.Unchecked
            )
            check.setData(Qt.ItemDataRole.UserRole, name)
            self.device_table.setItem(row, 0, check)

            self.device_table.setItem(row, 1, QTableWidgetItem(name))
            self.device_table.setItem(row, 2, QTableWidgetItem(str(index)))
            self.device_table.setItem(
                row,
                3,
                QTableWidgetItem(str(device.get("android_version", "?"))),
            )
            running = bool(device.get("is_process_started"))
            self.device_table.setItem(
                row, 4, QTableWidgetItem("Berjalan" if running else "Berhenti")
            )
            self.device_table.setItem(
                row, 5, QTableWidgetItem(", ".join(members.get(name, [])))
            )

        self.reload_groups()

    def checked_device_refs(self) -> list[DeviceRef]:
        refs: list[DeviceRef] = []
        for row in range(self.device_table.rowCount()):
            item = self.device_table.item(row, 0)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            name = item.data(Qt.ItemDataRole.UserRole)
            index_item = self.device_table.item(row, 2)
            refs.append(
                DeviceRef(
                    name=str(name),
                    index=index_item.text() if index_item else "",
                )
            )
        return refs

    def selected_group(self) -> str | None:
        item = self.group_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def reload_groups(self) -> None:
        selected = self.selected_group()
        self.group_list.blockSignals(True)
        self.group_list.clear()

        present_names = {
            str(device.get("name", "")).strip()
            for device in self.devices.values()
        }

        for name, group in self.group_store.load().items():
            total = len(group.devices)
            present = sum(1 for ref in group.devices if ref.name in present_names)
            missing = total - present
            label = f"{name}  —  {present}/{total} device"
            if missing:
                label += f"  ({missing} hilang)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            if group.last_preset:
                item.setToolTip(f"Preset terakhir: {group.last_preset}")
            self.group_list.addItem(item)
            if name == selected:
                self.group_list.setCurrentItem(item)

        if self.group_list.currentItem() is None and self.group_list.count() > 0:
            self.group_list.setCurrentRow(0)

        self.group_list.blockSignals(False)
        self._sync_buttons()

    def reload_presets(self) -> None:
        current = self.preset_combo.currentData()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for name, _changes, builtin in self.profile_store.all_profiles():
            label = name if not builtin else f"{name} (bawaan)"
            self.preset_combo.addItem(label, name)
        if current:
            index = self.preset_combo.findData(current)
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)
        self.preset_combo.blockSignals(False)
        self._sync_buttons()

    def set_retry_enabled(self, enabled: bool) -> None:
        self._retry_available = enabled
        self._sync_buttons()

    def set_busy(self, busy: bool) -> None:
        self.setEnabled(not busy)

    # ------------------------------------------------------------- progress
    def start_progress(self, targets: list[tuple[str, str]]) -> None:
        self.progress_table.setRowCount(0)
        self._progress_rows.clear()
        for name, index in targets:
            self._add_progress_row(name, index)
        self.set_retry_enabled(False)

    def _add_progress_row(self, name: str, index: str) -> int:
        row = self.progress_table.rowCount()
        self.progress_table.insertRow(row)
        self.progress_table.setItem(
            row, 0, QTableWidgetItem(f"{name}  (index {index})")
        )
        self.progress_table.setItem(row, 1, QTableWidgetItem("Menunggu"))
        self.progress_table.setItem(row, 2, QTableWidgetItem(""))
        self._progress_rows[name] = row
        return row

    def update_progress(self, payload: dict) -> None:
        name = str(payload.get("name", ""))
        row = self._progress_rows.get(name)
        if row is None:
            row = self._add_progress_row(name, str(payload.get("index", "?")))

        phase = str(payload.get("phase", ""))
        self.progress_table.item(row, 1).setText(
            PHASE_LABELS.get(phase, phase)
        )
        self.progress_table.item(row, 2).setText(
            str(payload.get("message", ""))
        )

        color = {
            "success": "#4ade80",
            "failed": "#f87171",
            "unchanged": "#9aa3b8",
            "skipped": "#fbbf24",
        }.get(str(payload.get("status", "")))
        if color:
            for column in (1, 2):
                self.progress_table.item(row, column).setForeground(
                    QColor(color)
                )

    # ---------------------------------------------------------------- crud
    def _membership_map(self) -> dict[str, list[str]]:
        members: dict[str, list[str]] = {}
        for group_name, group in self.group_store.load().items():
            for ref in group.devices:
                members.setdefault(ref.name, []).append(group_name)
        return members

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.device_table.rowCount()):
            item = self.device_table.item(row, 0)
            if item is not None:
                item.setCheckState(state)

    def _create_group(self) -> None:
        refs = self.checked_device_refs()
        if not refs:
            QMessageBox.information(
                self, "Belum ada pilihan", "Centang minimal satu device dulu."
            )
            return

        name, ok = QInputDialog.getText(self, "Buat Grup", "Nama grup:")
        name = name.strip()
        if not ok or not name:
            return

        try:
            self.group_store.create(name, refs)
        except ValueError as exc:
            QMessageBox.warning(self, "Gagal membuat grup", str(exc))
            return

        self._refresh_after_group_change(name)

    def _add_to_group(self) -> None:
        group = self.selected_group()
        if not group:
            QMessageBox.information(
                self, "Belum ada grup", "Pilih grup tujuan terlebih dahulu."
            )
            return
        refs = self.checked_device_refs()
        if not refs:
            QMessageBox.information(
                self, "Belum ada pilihan", "Centang device yang ingin ditambahkan."
            )
            return

        try:
            self.group_store.add_devices(group, refs)
        except ValueError as exc:
            QMessageBox.warning(self, "Gagal menambah device", str(exc))
            return

        self._refresh_after_group_change(group)

    def _remove_from_group(self) -> None:
        group = self.selected_group()
        if not group:
            return
        refs = self.checked_device_refs()
        if not refs:
            QMessageBox.information(
                self, "Belum ada pilihan", "Centang device yang ingin dikeluarkan."
            )
            return

        try:
            self.group_store.remove_devices(group, [ref.name for ref in refs])
        except ValueError as exc:
            QMessageBox.warning(self, "Gagal mengeluarkan device", str(exc))
            return

        self._refresh_after_group_change(group)

    def _rename_group(self) -> None:
        group = self.selected_group()
        if not group:
            return
        new_name, ok = QInputDialog.getText(
            self, "Ganti Nama Grup", "Nama baru:", text=group
        )
        new_name = new_name.strip()
        if not ok or not new_name:
            return
        try:
            renamed = self.group_store.rename(group, new_name)
        except ValueError as exc:
            QMessageBox.warning(self, "Gagal mengganti nama", str(exc))
            return
        self._refresh_after_group_change(renamed)

    def _delete_group(self) -> None:
        group = self.selected_group()
        if not group:
            return
        answer = QMessageBox.question(
            self, "Hapus Grup", f"Hapus grup '{group}'?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.group_store.delete(group)
        self._refresh_after_group_change(None)

    def _refresh_after_group_change(self, select: str | None) -> None:
        self.reload_groups()
        if select:
            for row in range(self.group_list.count()):
                item = self.group_list.item(row)
                if item.data(Qt.ItemDataRole.UserRole) == select:
                    self.group_list.setCurrentItem(item)
                    break
        # perbarui kolom "Grup" pada tabel device
        members = self._membership_map()
        for row in range(self.device_table.rowCount()):
            name_item = self.device_table.item(row, 1)
            if name_item is None:
                continue
            self.device_table.item(row, 5).setText(
                ", ".join(members.get(name_item.text(), []))
            )

    # -------------------------------------------------------------- signals
    def _sync_buttons(self) -> None:
        group = self.selected_group() is not None
        preset = self.preset_combo.currentData() is not None
        self.apply_button.setEnabled(group and preset)
        self.copy_button.setEnabled(group)
        self.add_button.setEnabled(group)
        self.remove_button.setEnabled(group)
        self.rename_group_button.setEnabled(group)
        self.delete_group_button.setEnabled(group)
        self.retry_button.setEnabled(self._retry_available)

    def _request_apply(self) -> None:
        group = self.selected_group()
        preset = self.preset_combo.currentData()
        if not group or not preset:
            return
        self.applyRequested.emit(
            group, str(preset), self.relaunch_check.isChecked()
        )

    def _request_copy(self) -> None:
        group = self.selected_group()
        if group:
            self.copyCurrentRequested.emit(group)

    def _load(self, settings: dict[str, str]) -> None:
        pass

    def collect(self) -> dict[str, str]:
        return {}
