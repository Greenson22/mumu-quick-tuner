"""Tab Otomatisasi: sesi grup, daftar aplikasi, dan script interaksi."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.automation import (
    AutomationApp,
    AutomationConfig,
    AutomationStore,
    KEY_LABELS,
    LOOP_MODES,
    ScriptStep,
    looks_like_package,
)
from app.services.automation_run import run_single_script_test
from app.services.recorder import ActionRecorder, find_mumu_windows, pick_window_under_cursor
from app.services.groups import GroupStore
from app.ui.sections import ScrollSection
from app.ui.widgets import Card, checkbox

PHASE_LABELS = {
    "batch": "Batch",
    "gap": "Menunggu jeda",
    "launch": "Menyalakan",
    "arrange": "Menata jendela",
    "wait": "Menunggu Android",
    "duration": "Durasi",
    "check": "Memeriksa aplikasi",
    "app": "Membuka aplikasi",
    "script": "Interaksi",
    "session": "Sesi berjalan",
    "shutdown": "Mematikan",
    "done": "Selesai",
    "error": "Gagal",
    "stop": "Dihentikan",
    "skip": "Dilewati",
}

STATUS_LABELS = {
    "success": "Berhasil",
    "failed": "Gagal",
    "skipped": "Dilewati",
    "stopped": "Dihentikan",
}


def _duration_text(seconds: int) -> str:
    if seconds <= 0:
        return "-"
    minutes, remainder = divmod(seconds, 60)
    if minutes:
        return f"{minutes}m {remainder:02d}s"
    return f"{seconds}s"


class StepDialog(QDialog):
    """Dialog untuk membuat/mengubah satu langkah script."""

    ACTION_LABELS = [
        ("tap", "Tap"),
        ("swipe", "Swipe"),
        ("wait", "Tunggu"),
        ("key", "Tombol"),
        ("text", "Ketik Teks"),
    ]

    def __init__(
        self, step: ScriptStep | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Langkah Interaksi")
        self.setMinimumWidth(420)

        initial = step or ScriptStep(action="tap")

        self.action_combo = QComboBox()
        for value, label in self.ACTION_LABELS:
            self.action_combo.addItem(label, value)
        self.action_combo.setCurrentIndex(
            max(0, self.action_combo.findData(initial.action))
        )

        self.tap_x = self._spin(0, 20000, initial.x)
        self.tap_y = self._spin(0, 20000, initial.y)
        self.swipe_x1 = self._spin(0, 20000, initial.x)
        self.swipe_y1 = self._spin(0, 20000, initial.y)
        self.swipe_x2 = self._spin(0, 20000, initial.x2)
        self.swipe_y2 = self._spin(0, 20000, initial.y2)
        self.swipe_duration = self._spin(50, 20000, initial.duration_ms, step=50)
        self.key_combo = QComboBox()
        for key, label in KEY_LABELS.items():
            self.key_combo.addItem(label, key)
        self.key_combo.setCurrentIndex(max(0, self.key_combo.findData(initial.key)))
        self.text_input = QLineEdit(initial.text)
        self.text_input.setPlaceholderText("Teks yang akan diketik di Android…")
        self.wait_spin = self._spin(0, 600000, initial.delay_ms, step=100)
        self.delay_spin = self._spin(0, 600000, initial.delay_ms, step=100)

        self.form = QFormLayout()
        self.form.setHorizontalSpacing(18)
        self.form.setVerticalSpacing(10)
        self.form.addRow("Jenis", self.action_combo)

        self._point_holder = self._pair(self.tap_x, self.tap_y)
        self.form.addRow("Koordinat tap x, y", self._point_holder)
        self._swipe_holder = self._two_pairs(
            self.swipe_x1, self.swipe_y1, self.swipe_x2, self.swipe_y2
        )
        self.form.addRow("Swipe dari → ke", self._swipe_holder)
        self.form.addRow("Durasi swipe (ms)", self.swipe_duration)
        self.form.addRow("Tombol", self.key_combo)
        self.form.addRow("Teks", self.text_input)
        self.form.addRow("Durasi tunggu (ms)", self.wait_spin)
        self.form.addRow("Jeda setelah aksi (ms)", self.delay_spin)

        note = QLabel(
            "Koordinat mengikuti resolusi referensi di tab Otomatisasi. "
            "Jika opsi skala aktif, koordinat disesuaikan ke resolusi device."
        )
        note.setObjectName("hint")
        note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        layout.addLayout(self.form)
        layout.addWidget(note)
        layout.addWidget(buttons)

        self.action_combo.currentIndexChanged.connect(self._sync_visibility)
        self._sync_visibility()

    @staticmethod
    def _spin(
        minimum: int, maximum: int, value: int, step: int = 1
    ) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setValue(max(minimum, min(maximum, value)))
        return spin

    @staticmethod
    def _pair(first: QSpinBox, second: QSpinBox) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(first)
        row.addWidget(QLabel("×"))
        row.addWidget(second)
        return holder

    @staticmethod
    def _two_pairs(
        x1: QSpinBox, y1: QSpinBox, x2: QSpinBox, y2: QSpinBox
    ) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(x1)
        row.addWidget(y1)
        row.addWidget(QLabel("→"))
        row.addWidget(x2)
        row.addWidget(y2)
        return holder

    def _action(self) -> str:
        return str(self.action_combo.currentData())

    def _sync_visibility(self) -> None:
        action = self._action()
        self._show_field(self._point_holder, action == "tap")
        self._show_field(self._swipe_holder, action == "swipe")
        self._show_field(self.swipe_duration, action == "swipe")
        self._show_field(self.key_combo, action == "key")
        self._show_field(self.text_input, action == "text")
        self._show_field(self.wait_spin, action == "wait")
        self._show_field(self.delay_spin, action != "wait")

    def _show_field(self, widget: QWidget, visible: bool) -> None:
        widget.setVisible(visible)
        label = self.form.labelForField(widget)
        if label is not None:
            label.setVisible(visible)

    def _accept(self) -> None:
        step = self.step()
        error = step.validation_error()
        if error:
            QMessageBox.warning(self, "Langkah tidak valid", error)
            return
        self.accept()

    def step(self) -> ScriptStep:
        action = self._action()
        if action == "wait":
            delay = self.wait_spin.value()
            step = ScriptStep(action="wait", delay_ms=delay)
            return step

        if action == "tap":
            return ScriptStep(
                action="tap",
                x=self.tap_x.value(),
                y=self.tap_y.value(),
                delay_ms=self.delay_spin.value(),
            )

        if action == "swipe":
            return ScriptStep(
                action="swipe",
                x=self.swipe_x1.value(),
                y=self.swipe_y1.value(),
                x2=self.swipe_x2.value(),
                y2=self.swipe_y2.value(),
                duration_ms=self.swipe_duration.value(),
                delay_ms=self.delay_spin.value(),
            )

        if action == "text":
            return ScriptStep(
                action="text",
                text=self.text_input.text().strip(),
                delay_ms=self.delay_spin.value(),
            )

        return ScriptStep(
            action="key",
            key=str(self.key_combo.currentData()),
            delay_ms=self.delay_spin.value(),
        )


class RecordDialog(QDialog):
    """Dialog untuk merekam aksi mouse & keyboard langsung dari jendela MuMu."""

    stepRecorded = pyqtSignal(object)

    def __init__(
        self,
        ref_width: int = 1280,
        ref_height: int = 720,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Perekam Aksi Otomatis (Macro Recorder)")
        self.resize(600, 460)
        self.ref_width = ref_width
        self.ref_height = ref_height

        self.recorder: ActionRecorder | None = None
        self.recorded_steps: list[ScriptStep] = []
        self._pick_countdown = 0
        self._pick_timer: QTimer | None = None

        self.window_combo = QComboBox()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_windows)
        self.pick_btn = QPushButton("🎯 Pilih dengan Klik…")
        self.pick_btn.setToolTip(
            "Klik tombol ini, lalu klik pada jendela emulator MuMu dalam 5 detik.\n"
            "Cara ini bisa mendeteksi jendela yang berjalan sebagai Administrator."
        )
        self.pick_btn.clicked.connect(self._start_pick)

        win_row = QHBoxLayout()
        win_row.addWidget(QLabel("Jendela Emulator:"))
        win_row.addWidget(self.window_combo, 1)
        win_row.addWidget(self.refresh_btn)
        win_row.addWidget(self.pick_btn)

        self.start_btn = QPushButton("● Mulai Rekam")
        self.start_btn.setObjectName("primary")
        self.stop_btn = QPushButton("■ Selesai Rekam (F10)")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)

        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(self.start_btn)
        ctrl_row.addWidget(self.stop_btn)
        ctrl_row.addStretch(1)

        self.status_label = QLabel(
            "Pilih jendela emulator acuan, lalu klik 'Mulai Rekam'.\n"
            "Jika jendela tidak terdeteksi otomatis, gunakan tombol "
            "'🎯 Pilih dengan Klik…' untuk memilih secara manual."
        )
        self.status_label.setObjectName("hint")
        self.status_label.setWordWrap(True)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["No", "Aksi", "Jeda"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.ok_button = box.button(QDialogButtonBox.StandardButton.Ok)
        if self.ok_button:
            self.ok_button.setText("Terapkan ke Script")
            self.ok_button.setEnabled(False)
        box.accepted.connect(self.accept)
        box.rejected.connect(self._cancel_and_reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        layout.addLayout(win_row)
        layout.addLayout(ctrl_row)
        layout.addWidget(self.status_label)
        layout.addWidget(self.table, 1)
        layout.addWidget(box)

        self.start_btn.clicked.connect(self._start_recording)
        self.stop_btn.clicked.connect(self._stop_recording)
        self.stepRecorded.connect(self._on_step_recorded)

        self._refresh_windows()

    def _refresh_windows(self) -> None:
        self.window_combo.clear()
        windows = find_mumu_windows()
        for hwnd, title in windows:
            self.window_combo.addItem(f"{title} (HWND: {hwnd})", hwnd)

        if not windows:
            self.window_combo.addItem(
                "Tidak terdeteksi — gunakan '🎯 Pilih dengan Klik…'", 0
            )
        self.start_btn.setEnabled(bool(windows))

    def _start_pick(self) -> None:
        self._pick_countdown = 5
        self.pick_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.status_label.setText(
            f"⏳ Klik pada jendela emulator MuMu dalam {self._pick_countdown} detik…"
        )
        self._pick_timer = QTimer(self)
        self._pick_timer.setInterval(1000)
        self._pick_timer.timeout.connect(self._pick_tick)
        self._pick_timer.start()

    def _pick_tick(self) -> None:
        self._pick_countdown -= 1

        result = pick_window_under_cursor()
        if result is not None:
            hwnd, title = result
            # Jangan tangkap klik pada dialog kita sendiri
            if hwnd != int(self.winId()):
                parent_hwnd = 0
                if self.parent() is not None:
                    parent_hwnd = int(self.parent().winId())
                if hwnd != parent_hwnd:
                    self._finish_pick(hwnd, title)
                    return

        if self._pick_countdown <= 0:
            self._finish_pick(0, "")
            return

        self.status_label.setText(
            f"⏳ Klik pada jendela emulator MuMu dalam {self._pick_countdown} detik…"
        )

    def _finish_pick(self, hwnd: int, title: str) -> None:
        if self._pick_timer:
            self._pick_timer.stop()
            self._pick_timer = None

        self.pick_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)

        if hwnd:
            label = f"{title} (HWND: {hwnd})" if title else f"Window (HWND: {hwnd})"
            idx = self.window_combo.findData(hwnd)
            if idx < 0:
                self.window_combo.insertItem(0, label, hwnd)
                self.window_combo.setCurrentIndex(0)
            else:
                self.window_combo.setCurrentIndex(idx)
            self.start_btn.setEnabled(True)
            self.status_label.setText(
                f"✅ Jendela berhasil dipilih: {label}\n"
                "Klik 'Mulai Rekam' untuk mulai merekam aksi."
            )
        else:
            self.start_btn.setEnabled(self.window_combo.currentData() not in (None, 0))
            self.status_label.setText(
                "⚠️ Tidak ada jendela yang terdeteksi. Coba lagi dengan "
                "'🎯 Pilih dengan Klik…' dan klik tepat di jendela emulator."
            )

    def _start_recording(self) -> None:
        hwnd = self.window_combo.currentData()
        if not hwnd:
            QMessageBox.warning(
                self, "Jendela belum dipilih",
                "Pilih jendela emulator MuMu terlebih dahulu.\n\n"
                "Jika jendela tidak muncul di daftar, gunakan tombol "
                "'🎯 Pilih dengan Klik…' untuk memilih secara manual.",
            )
            return

        self.recorded_steps.clear()
        self.table.setRowCount(0)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.refresh_btn.setEnabled(False)
        self.pick_btn.setEnabled(False)
        self.window_combo.setEnabled(False)
        if self.ok_button:
            self.ok_button.setEnabled(False)

        self.status_label.setText(
            "🔴 SEDANG MEREKAM… Silakan berinteraksi (klik, swipe, ketik) di jendela emulator. "
            "Tekan tombol 'Selesai Rekam' atau shortcut F10 saat selesai."
        )

        self.recorder = ActionRecorder(
            target_hwnd=hwnd,
            ref_width=self.ref_width,
            ref_height=self.ref_height,
            on_step_recorded=lambda step: self.stepRecorded.emit(step),
        )
        self.recorder.start()

    def _stop_recording(self) -> None:
        if self.recorder:
            steps = self.recorder.stop()
            self.recorded_steps = steps
            self.recorder = None

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.refresh_btn.setEnabled(True)
        self.pick_btn.setEnabled(True)
        self.window_combo.setEnabled(True)
        if self.ok_button:
            self.ok_button.setEnabled(bool(self.recorded_steps))

        self.status_label.setText(
            f"Perekaman selesai. Total {len(self.recorded_steps)} aksi berhasil direkam. "
            "Klik 'Terapkan ke Script' untuk menyimpan."
        )

    def _on_step_recorded(self, step: ScriptStep) -> None:
        self.recorded_steps.append(step)
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.table.setItem(row, 1, QTableWidgetItem(step.describe()))
        self.table.setItem(row, 2, QTableWidgetItem(f"{step.delay_ms} ms"))
        self.table.scrollToBottom()

    def _cancel_and_reject(self) -> None:
        if self.recorder:
            self.recorder.stop()
            self.recorder = None
        self.reject()

    def closeEvent(self, event) -> None:
        if self._pick_timer:
            self._pick_timer.stop()
        if self.recorder:
            self.recorder.stop()
            self.recorder = None
        super().closeEvent(event)


class ScriptTestWorker(QThread):
    """Worker QThread aman untuk menjalankan uji coba skrip tanpa membekukan antarmuka."""

    progressSignal = pyqtSignal(dict)
    finishedSignal = pyqtSignal(list)
    failedSignal = pyqtSignal(str)

    def __init__(
        self,
        client,
        index: str,
        steps: list[ScriptStep],
        package: str,
        config: AutomationConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.index = index
        self.steps = steps
        self.package = package
        self.config = config
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    def run(self) -> None:
        try:
            errs = run_single_script_test(
                client=self.client,
                index=self.index,
                steps=self.steps,
                package=self.package,
                config=self.config,
                progress=lambda p: self.progressSignal.emit(p),
                should_stop=lambda: self._stopped,
            )
            self.finishedSignal.emit(errs)
        except Exception as exc:  # noqa: BLE001
            self.failedSignal.emit(str(exc))


class ScriptTestDialog(QDialog):
    """Dialog untuk menguji coba langkah skrip langsung pada satu device."""

    def __init__(
        self,
        client,
        app: AutomationApp,
        steps: list[ScriptStep],
        config: AutomationConfig | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Uji Coba Script — {app.display_name}")
        self.resize(520, 320)
        self.client = client
        self.app = app
        self.steps = list(steps)
        self.config = config or AutomationConfig()

        self._worker: ScriptTestWorker | None = None
        self._device_data: dict[str, dict] = {}

        self.device_combo = QComboBox()
        self.refresh_btn = QPushButton("Refresh Device")
        self.refresh_btn.clicked.connect(self._refresh_devices)

        dev_row = QHBoxLayout()
        dev_row.addWidget(QLabel("Target Device:"))
        dev_row.addWidget(self.device_combo, 1)
        dev_row.addWidget(self.refresh_btn)

        self.launch_app_check = checkbox("Buka aplikasi sebelum mulai")
        self.launch_app_check.setChecked(bool(self.app.package))

        delay_holder = QWidget()
        delay_row = QHBoxLayout(delay_holder)
        delay_row.setContentsMargins(0, 0, 0, 0)
        delay_row.setSpacing(8)
        self.start_delay_spin = QSpinBox()
        self.start_delay_spin.setRange(0, 300)
        self.start_delay_spin.setSuffix(" detik")
        self.start_delay_spin.setValue(self.config.script_start_delay_sec)
        delay_row.addWidget(QLabel("Waktu tunggu setelah buka app:"))
        delay_row.addWidget(self.start_delay_spin)
        delay_row.addStretch(1)

        self.start_btn = QPushButton("▶ Mulai Uji Coba")
        self.start_btn.setObjectName("primary")
        self.stop_btn = QPushButton("■ Hentikan")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)

        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(self.start_btn)
        ctrl_row.addWidget(self.stop_btn)
        ctrl_row.addStretch(1)

        self.status_label = QLabel(
            f"Total {len(self.steps)} langkah siap diuji. "
            "Pilih device yang sedang aktif lalu klik 'Mulai Uji Coba'."
        )
        self.status_label.setObjectName("hint")
        self.status_label.setWordWrap(True)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self._on_close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        layout.addLayout(dev_row)
        layout.addWidget(self.launch_app_check)
        layout.addWidget(delay_holder)
        layout.addLayout(ctrl_row)
        layout.addWidget(self.status_label, 1)
        layout.addWidget(close_box)

        self.start_btn.clicked.connect(self._start_test)
        self.stop_btn.clicked.connect(self._stop_test)

        self._refresh_devices()

    def _refresh_devices(self) -> None:
        self.device_combo.clear()
        self._device_data.clear()
        if not self.client:
            self.device_combo.addItem("Client tidak tersedia", "")
            self.start_btn.setEnabled(False)
            return

        try:
            self._device_data = self.client.list_devices()
        except Exception:
            self._device_data = {}

        ready_count = 0
        for index, dev in sorted(self._device_data.items(), key=lambda x: str(x[0])):
            name = dev.get("name", f"Device {index}")
            is_ready = bool(dev.get("is_android_started"))
            status_text = " [Android Siap]" if is_ready else " [Mati / Belum Siap]"
            self.device_combo.addItem(f"{name} (index {index}){status_text}", str(index))
            if is_ready:
                ready_count += 1
                if ready_count == 1:
                    self.device_combo.setCurrentIndex(self.device_combo.count() - 1)

        if not self._device_data:
            self.device_combo.addItem("Tidak ada device terdeteksi", "")
            self.start_btn.setEnabled(False)
        else:
            self.start_btn.setEnabled(True)

    def _start_test(self) -> None:
        index = str(self.device_combo.currentData() or "").strip()
        if not index:
            QMessageBox.warning(self, "Pilih Device", "Pilih device target terlebih dahulu.")
            return

        if not self.steps:
            QMessageBox.information(self, "Script Kosong", "Belum ada langkah script untuk diuji.")
            return

        # Cek apakah device sedang menyala
        dev_info = self._device_data.get(index, {})
        if not dev_info.get("is_android_started"):
            QMessageBox.warning(
                self,
                "Device Belum Siap",
                f"Device dengan index {index} belum menyala atau Android belum siap.\n\n"
                "Silakan nyalakan device terlebih dahulu (misal lewat MuMu Player atau tab Grup) "
                "sebelum menguji coba skrip.",
            )
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.refresh_btn.setEnabled(False)
        self.device_combo.setEnabled(False)
        self.launch_app_check.setEnabled(False)
        self.start_delay_spin.setEnabled(False)

        cfg = AutomationConfig(
            script_start_delay_sec=self.start_delay_spin.value(),
            reference_width=self.config.reference_width,
            reference_height=self.config.reference_height,
            scale_coordinates=self.config.scale_coordinates,
            interaction_enabled=True,
        )

        package_to_open = self.app.package if self.launch_app_check.isChecked() else ""

        self._worker = ScriptTestWorker(
            client=self.client,
            index=index,
            steps=self.steps,
            package=package_to_open,
            config=cfg,
            parent=self,
        )
        self._worker.progressSignal.connect(self._on_progress)
        self._worker.finishedSignal.connect(self._on_finished)
        self._worker.failedSignal.connect(self._on_failed)
        self._worker.start()

    def _stop_test(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop()
        self.status_label.setText("Menghentikan uji coba script…")

    def _on_progress(self, payload: dict) -> None:
        msg = str(payload.get("message", ""))
        self.status_label.setText(msg)

    def _on_finished(self, errors: list) -> None:
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.refresh_btn.setEnabled(True)
        self.device_combo.setEnabled(True)
        self.launch_app_check.setEnabled(True)
        self.start_delay_spin.setEnabled(True)

        if not errors:
            self.status_label.setText("✅ Uji coba selesai! Semua langkah berhasil dijalankan.")
        else:
            err_summary = "\n• " + "\n• ".join(errors[:5])
            self.status_label.setText(f"Selesai dengan catatan:{err_summary}")

    def _on_failed(self, error_message: str) -> None:
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.refresh_btn.setEnabled(True)
        self.device_combo.setEnabled(True)
        self.launch_app_check.setEnabled(True)
        self.start_delay_spin.setEnabled(True)
        self.status_label.setText(f"❌ Terjadi kesalahan saat uji coba: {error_message}")

    def _on_close(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(1500)
        self.reject()

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(1500)
        super().closeEvent(event)


class ScriptDialog(QDialog):
    """Editor daftar langkah untuk satu aplikasi."""

    def __init__(
        self,
        app: AutomationApp,
        ref_width: int = 1280,
        ref_height: int = 720,
        client=None,
        config: AutomationConfig | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Script — {app.display_name}")
        self.resize(780, 450)
        self.app = app
        self.ref_width = ref_width
        self.ref_height = ref_height
        self.client = client
        self.config = config or AutomationConfig()
        self.steps = [ScriptStep.from_dict(step.to_dict()) for step in app.steps]
        self.result_steps: list[ScriptStep] = []

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["No", "Aksi", "Detail", "Jeda"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(lambda _index: self._edit())

        buttons = QHBoxLayout()

        record_btn = QPushButton("● Rekam Aksi…")
        record_btn.setObjectName("primary")
        test_btn = QPushButton("▶ Uji di Device…")

        add_menu_btn = QPushButton("+ Tambah Manual ▾")
        add_menu = QMenu(add_menu_btn)
        add_menu.addAction("👆 + Tap (Klik)").triggered.connect(lambda: self._add("tap"))
        add_menu.addAction("↔️ + Swipe (Geser)").triggered.connect(lambda: self._add("swipe"))
        add_menu.addAction("⏳ + Tunggu (Delay)").triggered.connect(lambda: self._add("wait"))
        add_menu.addAction("⌨️ + Ketik Teks").triggered.connect(lambda: self._add("text"))
        add_menu.addAction("🔲 + Tombol (Back/Home/dll)").triggered.connect(lambda: self._add("key"))
        add_menu_btn.setMenu(add_menu)

        edit = QPushButton("Ubah…")
        remove = QPushButton("Hapus")
        up = QPushButton("↑ Naik")
        down = QPushButton("↓ Turun")

        buttons.addWidget(record_btn)
        buttons.addWidget(test_btn)
        buttons.addWidget(add_menu_btn)
        buttons.addSpacing(16)
        buttons.addWidget(edit)
        buttons.addWidget(remove)
        buttons.addWidget(up)
        buttons.addWidget(down)
        buttons.addStretch(1)

        note = QLabel(
            "Klik '● Rekam Aksi…' untuk merekam langsung dari emulator. "
            "Gunakan '▶ Uji di Device…' untuk mencoba skrip langsung di satu device."
        )
        note.setObjectName("hint")
        note.setWordWrap(True)

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        layout.addWidget(self.table, 1)
        layout.addLayout(buttons)
        layout.addWidget(note)
        layout.addWidget(box)

        record_btn.clicked.connect(self._record)
        test_btn.clicked.connect(self._test_script)
        edit.clicked.connect(self._edit)
        remove.clicked.connect(self._remove)
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))

        self._refresh()

    def _test_script(self) -> None:
        if not self.steps:
            QMessageBox.information(
                self, "Script Kosong", "Tambahkan atau rekam minimal satu langkah terlebih dahulu."
            )
            return
        dialog = ScriptTestDialog(
            client=self.client,
            app=self.app,
            steps=self.steps,
            config=self.config,
            parent=self,
        )
        dialog.exec()

    def _refresh(self) -> None:
        self.table.setRowCount(0)
        for index, step in enumerate(self.steps):
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(index + 1)))
            self.table.setItem(row, 1, QTableWidgetItem(step.describe()))
            self.table.setItem(row, 2, QTableWidgetItem(self._detail(step)))
            self.table.setItem(
                row, 3, QTableWidgetItem(f"{step.delay_ms} ms")
            )
        if self.steps:
            self.table.selectRow(min(len(self.steps) - 1, 0))

    @staticmethod
    def _detail(step: ScriptStep) -> str:
        if step.action == "tap":
            return f"x={step.x}, y={step.y}"
        if step.action == "swipe":
            return (
                f"({step.x},{step.y}) → ({step.x2},{step.y2}), "
                f"{step.duration_ms} ms"
            )
        if step.action == "wait":
            return f"{step.delay_ms} ms"
        if step.action == "text":
            return f'"{step.text}"'
        return KEY_LABELS.get(step.key, step.key)

    def _selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _add(self, action: str) -> None:
        dialog = StepDialog(ScriptStep(action=action), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.steps.append(dialog.step())
            self._refresh()

    def _record(self) -> None:
        dialog = RecordDialog(
            ref_width=self.ref_width,
            ref_height=self.ref_height,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.recorded_steps:
                self.steps.extend(dialog.recorded_steps)
                self._refresh()

    def _edit(self) -> None:
        row = self._selected_row()
        if row < 0 or row >= len(self.steps):
            return
        dialog = StepDialog(self.steps[row], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.steps[row] = dialog.step()
            self._refresh()

    def _remove(self) -> None:
        row = self._selected_row()
        if 0 <= row < len(self.steps):
            del self.steps[row]
            self._refresh()

    def _move(self, delta: int) -> None:
        row = self._selected_row()
        target = row + delta
        if row < 0 or not (0 <= target < len(self.steps)):
            return
        self.steps[row], self.steps[target] = self.steps[target], self.steps[row]
        self._refresh()
        self.table.selectRow(target)

    def _accept(self) -> None:
        for index, step in enumerate(self.steps, start=1):
            error = step.validation_error()
            if error:
                QMessageBox.warning(
                    self, "Script tidak valid", f"Langkah {index}: {error}"
                )
                return
        self.result_steps = list(self.steps)
        self.accept()


class AddAppDialog(QDialog):
    """Tambah aplikasi secara manual berdasarkan nama paket."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tambah Aplikasi")
        self.setMinimumWidth(420)

        self.package_edit = QLineEdit()
        self.package_edit.setPlaceholderText("mis. com.whatsapp")
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("opsional, mis. WhatsApp")

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow("Nama paket", self.package_edit)
        form.addRow("Nama tampilan", self.label_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        package = self.package_edit.text().strip()
        if not looks_like_package(package):
            QMessageBox.warning(
                self,
                "Paket tidak valid",
                "Nama paket harus mengandung titik dan tanpa spasi, "
                "misalnya com.whatsapp.",
            )
            return
        self.accept()

    def values(self) -> tuple[str, str]:
        return (
            self.package_edit.text().strip(),
            self.label_edit.text().strip(),
        )


class AppPickerDialog(QDialog):
    """Pilih satu atau beberapa aplikasi dari daftar terpasang."""

    def __init__(
        self,
        apps: list[tuple[str, str]],
        existing: set[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tambah dari Device")
        self.resize(520, 420)

        self.list = QListWidget()
        for package, label in apps:
            if package in existing:
                continue
            text = f"{label} — {package}" if label and label != package else package
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, package)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list.addItem(item)

        select_all = QPushButton("Pilih Semua")
        clear = QPushButton("Kosongkan")
        select_all.clicked.connect(lambda: self._set_all(True))
        clear.clicked.connect(lambda: self._set_all(False))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        row = QHBoxLayout()
        row.addWidget(select_all)
        row.addWidget(clear)
        row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        layout.addWidget(self.list, 1)
        layout.addLayout(row)
        layout.addWidget(buttons)

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.list.count()):
            self.list.item(row).setCheckState(state)

    def selected(self) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                text = item.text()
                label = text.split(" — ", 1)[0] if " — " in text else ""
                result.append((str(item.data(Qt.ItemDataRole.UserRole)), label))
        return result


class AutomationSection(ScrollSection):
    startRequested = pyqtSignal(str)  # group
    stopRequested = pyqtSignal()
    loadAppsRequested = pyqtSignal(str)  # group

    def __init__(
        self,
        group_store: GroupStore,
        automation_store: AutomationStore | None = None,
        client=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.group_store = group_store
        self.store = automation_store or AutomationStore()
        self.client = client
        self.config: AutomationConfig = self.store.load()
        self.installed_apps: list[tuple[str, str]] = []
        self._rows: dict[str, int] = {}
        self._running = False
        self._loading = False

        self._build_session_card()
        self._build_apps_card()
        self._build_progress_card()
        self._apply_config_to_widgets()
        self._reload_apps_table()
        self._sync_buttons()

    # ------------------------------------------------------------------ UI
    def _build_session_card(self) -> None:
        card = Card(
            "Grup & sesi",
            "Otomatisasi menyalakan device per batch, membuka aplikasi, "
            "menjalankan script, lalu mematikan device. Batch berikutnya dimulai "
            "setelah batch sebelumnya selesai.",
        )

        self.group_combo = QComboBox()
        self.group_combo.setMinimumWidth(280)
        card.add_row("Grup", self.group_combo)

        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 64)
        self.batch_spin.setSuffix(" device")
        card.add_row("Device per batch", self.batch_spin)

        self.gap_spin = QSpinBox()
        self.gap_spin.setRange(0, 600)
        self.gap_spin.setSuffix(" detik")
        card.add_row(
            "Jeda antar device",
            self.gap_spin,
            "Waktu tunggu sebelum menyalakan/mengeksekusi device berikutnya. "
            "Bisa ditentukan (misal 60 detik).",
        )

        loop_holder = QWidget()
        loop_row = QHBoxLayout(loop_holder)
        loop_row.setContentsMargins(0, 0, 0, 0)
        loop_row.setSpacing(8)

        self.loop_mode_combo = QComboBox()
        self.loop_mode_combo.addItem("Sekali jalan (tanpa loop)", "none")
        self.loop_mode_combo.addItem("Ulangi N kali", "count")
        self.loop_mode_combo.addItem("Infinite Loop (tanpa henti)", "infinite")

        self.loop_count_spin = QSpinBox()
        self.loop_count_spin.setRange(1, 9999)
        self.loop_count_spin.setSuffix(" kali")
        self.loop_count_spin.setValue(1)

        loop_row.addWidget(self.loop_mode_combo)
        loop_row.addWidget(self.loop_count_spin)
        loop_row.addStretch(1)
        card.add_row("Pengulangan (Loop)", loop_holder)

        self.loop_delay_spin = QSpinBox()
        self.loop_delay_spin.setRange(0, 3600)
        self.loop_delay_spin.setSuffix(" detik")
        card.add_row(
            "Jeda antar pengulangan",
            self.loop_delay_spin,
            "Waktu istirahat setelah semua batch/device selesai sebelum mengulang lagi. "
            "Default 60 detik.",
        )

        self.arrange_check = checkbox(
            "Susun jendela device otomatis (tidak tumpang tindih)"
        )
        card.add_row("Posisi jendela", self.arrange_check)

        duration_holder = QWidget()
        duration_row = QHBoxLayout(duration_holder)
        duration_row.setContentsMargins(0, 0, 0, 0)
        duration_row.setSpacing(8)
        self.minutes_min = QDoubleSpinBox()
        self.minutes_min.setRange(0.1, 720.0)
        self.minutes_min.setDecimals(1)
        self.minutes_min.setSingleStep(0.5)
        self.minutes_min.setSuffix(" menit")
        self.minutes_max = QDoubleSpinBox()
        self.minutes_max.setRange(0.1, 720.0)
        self.minutes_max.setDecimals(1)
        self.minutes_max.setSingleStep(0.5)
        self.minutes_max.setSuffix(" menit")
        duration_row.addWidget(QLabel("Min"))
        duration_row.addWidget(self.minutes_min)
        duration_row.addWidget(QLabel("Maks"))
        duration_row.addWidget(self.minutes_max)
        duration_row.addStretch(1)
        card.add_row("Durasi acak per device", duration_holder)

        self.interaction_check = checkbox(
            "Aktifkan interaksi otomatis (script koordinat)"
        )
        card.add_row("Interaksi", self.interaction_check)

        self.script_start_delay_spin = QSpinBox()
        self.script_start_delay_spin.setRange(0, 300)
        self.script_start_delay_spin.setSuffix(" detik")
        card.add_row(
            "Waktu mulai script",
            self.script_start_delay_spin,
            "Waktu tunggu setelah aplikasi dibuka sebelum langkah pertama dijalankan. "
            "Memberi waktu loading/splash screen.",
        )

        scale_holder = QWidget()
        scale_row = QHBoxLayout(scale_holder)
        scale_row.setContentsMargins(0, 0, 0, 0)
        scale_row.setSpacing(8)
        self.scale_check = checkbox("Skalakan koordinat")
        self.ref_width = QSpinBox()
        self.ref_width.setRange(1, 20000)
        self.ref_width.setSuffix(" px")
        self.ref_height = QSpinBox()
        self.ref_height.setRange(1, 20000)
        self.ref_height.setSuffix(" px")
        scale_row.addWidget(self.scale_check)
        scale_row.addWidget(QLabel("Referensi"))
        scale_row.addWidget(self.ref_width)
        scale_row.addWidget(QLabel("×"))
        scale_row.addWidget(self.ref_height)
        scale_row.addStretch(1)
        card.add_row("Resolusi script", scale_holder)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("Mulai Otomatisasi")
        self.start_button.setObjectName("primary")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("danger")
        self.stop_button.setEnabled(False)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        buttons.addStretch(1)
        card.form.addRow(buttons)

        self.status_label = QLabel("Siap.")
        self.status_label.setObjectName("hint")
        self.status_label.setWordWrap(True)
        card.form.addRow(self.status_label)

        self.add_card(card)

        for widget in (
            self.batch_spin,
            self.gap_spin,
            self.minutes_min,
            self.minutes_max,
            self.ref_width,
            self.ref_height,
            self.loop_count_spin,
            self.loop_delay_spin,
            self.script_start_delay_spin,
        ):
            widget.valueChanged.connect(self._save_config)
        self.loop_mode_combo.currentIndexChanged.connect(self._on_loop_mode_changed)
        self.arrange_check.toggled.connect(self._save_config)
        self.interaction_check.toggled.connect(self._save_config)
        self.scale_check.toggled.connect(self._save_config)
        self.group_combo.currentIndexChanged.connect(self._sync_buttons)
        self.start_button.clicked.connect(self._start)
        self.stop_button.clicked.connect(self._stop)

    def _on_loop_mode_changed(self) -> None:
        mode = str(self.loop_mode_combo.currentData())
        self.loop_count_spin.setVisible(mode == "count")
        self.loop_delay_spin.setEnabled(mode != "none")
        self._save_config()

    def _build_apps_card(self) -> None:
        card = Card(
            "Aplikasi otomatisasi (global)",
            "Daftar ini dipakai semua grup. Jika salah satu aplikasi aktif tidak "
            "terpasang di device, device tersebut dimatikan dan dicatat gagal.",
        )

        self.apps_table = QTableWidget(0, 4)
        self.apps_table.setHorizontalHeaderLabels(
            ["Aktif", "Aplikasi", "Paket", "Script"]
        )
        self.apps_table.verticalHeader().setVisible(False)
        self.apps_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.apps_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.apps_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.apps_table.setAlternatingRowColors(True)
        self.apps_table.setMinimumHeight(180)
        header = self.apps_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        card.form.addRow(self.apps_table)

        buttons = QHBoxLayout()
        self.add_app_button = QPushButton("Tambah Manual…")
        self.add_device_button = QPushButton("Tambah dari Device…")
        self.edit_script_button = QPushButton("Edit Script…")
        self.remove_app_button = QPushButton("Hapus")
        self.remove_app_button.setObjectName("danger")
        self.up_app_button = QPushButton("Naik")
        self.down_app_button = QPushButton("Turun")
        for button in (
            self.add_app_button,
            self.add_device_button,
            self.edit_script_button,
            self.remove_app_button,
            self.up_app_button,
            self.down_app_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        card.form.addRow(buttons)

        self.add_card(card)

        self.apps_table.itemChanged.connect(self._on_app_item_changed)
        self.apps_table.itemSelectionChanged.connect(self._sync_buttons)
        self.add_app_button.clicked.connect(self._add_app_manual)
        self.add_device_button.clicked.connect(self._request_installed_apps)
        self.edit_script_button.clicked.connect(self._edit_script)
        self.remove_app_button.clicked.connect(self._remove_app)
        self.up_app_button.clicked.connect(lambda: self._move_app(-1))
        self.down_app_button.clicked.connect(lambda: self._move_app(1))

    def _build_progress_card(self) -> None:
        card = Card(
            "Progres otomatisasi",
            "Status per device selama sesi berjalan. Laporan lengkap disimpan "
            "sebagai file JSON setelah sesi selesai.",
        )

        self.progress_table = QTableWidget(0, 6)
        self.progress_table.setHorizontalHeaderLabels(
            ["Device", "Batch", "Status", "Aplikasi", "Durasi", "Keterangan"]
        )
        self.progress_table.verticalHeader().setVisible(False)
        self.progress_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.progress_table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.progress_table.setAlternatingRowColors(True)
        self.progress_table.setMinimumHeight(200)
        header = self.progress_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        card.form.addRow(self.progress_table)
        self.report_label = QLabel("Belum ada laporan.")
        self.report_label.setObjectName("hint")
        self.report_label.setWordWrap(True)
        card.form.addRow(self.report_label)
        self.add_card(card)

    # -------------------------------------------------------------- public
    def reload_groups(self) -> None:
        current = self.selected_group()
        names = list(self.group_store.load().keys())
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        for name in names:
            self.group_combo.addItem(name, name)
        if current:
            index = self.group_combo.findData(current)
            if index >= 0:
                self.group_combo.setCurrentIndex(index)
        self.group_combo.blockSignals(False)
        self._sync_buttons()

    def select_group(self, name: str) -> None:
        index = self.group_combo.findData(name)
        if index >= 0:
            self.group_combo.setCurrentIndex(index)

    def selected_group(self) -> str | None:
        return self.group_combo.currentData()

    def set_installed_apps(self, apps: list[tuple[str, str]]) -> None:
        self.installed_apps = list(apps)

    def add_apps_from_list(self, apps: list[tuple[str, str]]) -> None:
        self.set_installed_apps(apps)
        existing = {app.package for app in self.config.apps}
        dialog = AppPickerDialog(apps, existing, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = dialog.selected()
        if not selected:
            QMessageBox.information(
                self, "Tidak ada pilihan", "Pilih minimal satu aplikasi."
            )
            return
        for package, label in selected:
            self.config.apps.append(
                AutomationApp(package=package, label=label, enabled=True)
            )
        self._persist()
        self._reload_apps_table()

    def set_running(self, running: bool) -> None:
        self._running = running
        for widget in (
            self.group_combo,
            self.batch_spin,
            self.gap_spin,
            self.minutes_min,
            self.minutes_max,
            self.loop_mode_combo,
            self.loop_count_spin,
            self.loop_delay_spin,
            self.script_start_delay_spin,
            self.arrange_check,
            self.interaction_check,
            self.scale_check,
            self.ref_width,
            self.ref_height,
            self.apps_table,
            self.add_app_button,
            self.add_device_button,
            self.edit_script_button,
            self.remove_app_button,
            self.up_app_button,
            self.down_app_button,
        ):
            widget.setEnabled(not running)
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        if running:
            self.status_label.setText("Otomatisasi berjalan…")
        self._sync_buttons()

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def set_report_path(self, path: str) -> None:
        self.report_label.setText(f"Laporan: {path}")

    # ------------------------------------------------------------- progress
    def start_progress(
        self,
        targets: list[tuple[str, str]],
        missing: list[tuple[str, str]],
        batch_size: int,
    ) -> None:
        self.progress_table.setRowCount(0)
        self._rows.clear()
        for position, (name, index) in enumerate(targets):
            batch = position // max(1, batch_size) + 1
            self._add_row(name, index, batch)
        for name, index in missing:
            self._add_row(name, index, "-")
            row = self._rows[name]
            self.progress_table.item(row, 2).setText("Dilewati")
            self.progress_table.item(row, 5).setText("Device tidak ditemukan.")
            self.progress_table.item(row, 2).setForeground(QColor("#fbbf24"))

    def _add_row(self, name: str, index: str, batch: int | str) -> int:
        row = self.progress_table.rowCount()
        self.progress_table.insertRow(row)
        self.progress_table.setItem(
            row, 0, QTableWidgetItem(f"{name}  (index {index})")
        )
        self.progress_table.setItem(row, 1, QTableWidgetItem(str(batch)))
        self.progress_table.setItem(row, 2, QTableWidgetItem("Menunggu"))
        self.progress_table.setItem(row, 3, QTableWidgetItem(""))
        self.progress_table.setItem(row, 4, QTableWidgetItem("-"))
        self.progress_table.setItem(row, 5, QTableWidgetItem(""))
        self._rows[name] = row
        return row

    def update_progress(self, payload: dict) -> None:
        name = str(payload.get("name", ""))
        if not name:
            self.status_label.setText(str(payload.get("message", "")))
            return

        row = self._rows.get(name)
        if row is None:
            row = self._add_row(
                name,
                str(payload.get("index", "?")),
                payload.get("batch", "-"),
            )

        if payload.get("batch"):
            self.progress_table.item(row, 1).setText(str(payload["batch"]))

        phase = str(payload.get("phase", ""))
        status = str(payload.get("status", ""))

        if "remaining_sec" in payload and phase == "session":
            rem = int(payload["remaining_sec"])
            dur = int(payload.get("duration", 0))
            if dur > 0:
                self.progress_table.item(row, 4).setText(
                    f"{_duration_text(rem)} / {_duration_text(dur)}"
                )
            else:
                self.progress_table.item(row, 4).setText(_duration_text(rem))
        elif "remaining_sec" in payload and phase == "gap":
            rem = int(payload["remaining_sec"])
            self.progress_table.item(row, 4).setText(f"Jeda {rem}s")
        elif payload.get("duration"):
            self.progress_table.item(row, 4).setText(
                _duration_text(int(payload["duration"]))
            )

        apps = payload.get("apps_opened")
        if isinstance(apps, list) and apps:
            self.progress_table.item(row, 3).setText(", ".join(apps))

        label = STATUS_LABELS.get(status) or PHASE_LABELS.get(phase, phase)
        self.progress_table.item(row, 2).setText(label)
        self.progress_table.item(row, 5).setText(
            str(payload.get("message", ""))
        )

        color = {
            "success": "#4ade80",
            "failed": "#f87171",
            "skipped": "#fbbf24",
            "stopped": "#fbbf24",
        }.get(status)
        if color:
            for column in (2, 5):
                self.progress_table.item(row, column).setForeground(
                    QColor(color)
                )

    # --------------------------------------------------------------- config
    def _apply_config_to_widgets(self) -> None:
        self._loading = True
        try:
            self.batch_spin.setValue(self.config.batch_size)
            self.gap_spin.setValue(self.config.device_gap_sec)
            self.minutes_min.setValue(self.config.duration_min_sec / 60)
            self.minutes_max.setValue(self.config.duration_max_sec / 60)
            loop_idx = max(0, self.loop_mode_combo.findData(self.config.loop_mode))
            self.loop_mode_combo.setCurrentIndex(loop_idx)
            self.loop_count_spin.setValue(self.config.loop_count)
            self.loop_delay_spin.setValue(self.config.loop_delay_sec)
            self.loop_count_spin.setVisible(self.config.loop_mode == "count")
            self.loop_delay_spin.setEnabled(self.config.loop_mode != "none")
            self.arrange_check.setChecked(self.config.arrange_windows)
            self.interaction_check.setChecked(self.config.interaction_enabled)
            self.scale_check.setChecked(self.config.scale_coordinates)
            self.ref_width.setValue(self.config.reference_width)
            self.ref_height.setValue(self.config.reference_height)
            self.script_start_delay_spin.setValue(self.config.script_start_delay_sec)
        finally:
            self._loading = False

    def _collect_config(self) -> AutomationConfig:
        config = AutomationConfig(
            batch_size=self.batch_spin.value(),
            duration_min_sec=max(1, int(round(self.minutes_min.value() * 60))),
            duration_max_sec=max(1, int(round(self.minutes_max.value() * 60))),
            device_gap_sec=self.gap_spin.value(),
            loop_mode=str(self.loop_mode_combo.currentData()),
            loop_count=self.loop_count_spin.value(),
            loop_delay_sec=self.loop_delay_spin.value(),
            script_start_delay_sec=self.script_start_delay_spin.value(),
            arrange_windows=self.arrange_check.isChecked(),
            interaction_enabled=self.interaction_check.isChecked(),
            scale_coordinates=self.scale_check.isChecked(),
            reference_width=self.ref_width.value(),
            reference_height=self.ref_height.value(),
            apps=[
                AutomationApp.from_dict(app.to_dict())
                for app in self.config.apps
            ],
        )
        for row, app in enumerate(config.apps):
            item = self.apps_table.item(row, 0)
            if item is not None:
                app.enabled = item.checkState() == Qt.CheckState.Checked
        return config

    def _save_config(self, *_args) -> None:
        if self._loading:
            return
        self.config = self._collect_config()
        self.store.save(self.config)

    def _persist(self) -> None:
        """Simpan perubahan struktural tanpa membaca ulang tabel."""
        if self._loading:
            return
        self.store.save(self.config)

    def _reload_apps_table(self) -> None:
        self._loading = True
        self.apps_table.blockSignals(True)
        try:
            self.apps_table.setRowCount(0)
            for app in self.config.apps:
                row = self.apps_table.rowCount()
                self.apps_table.insertRow(row)
                check = QTableWidgetItem()
                check.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                check.setCheckState(
                    Qt.CheckState.Checked
                    if app.enabled
                    else Qt.CheckState.Unchecked
                )
                self.apps_table.setItem(row, 0, check)
                self.apps_table.setItem(
                    row, 1, QTableWidgetItem(app.display_name)
                )
                self.apps_table.setItem(
                    row, 2, QTableWidgetItem(app.package)
                )
                steps = f"{len(app.steps)} langkah" if app.steps else "-"
                self.apps_table.setItem(row, 3, QTableWidgetItem(steps))
        finally:
            self.apps_table.blockSignals(False)
            self._loading = False
        self._sync_buttons()

    def _on_app_item_changed(self, _item: QTableWidgetItem) -> None:
        if self._loading:
            return
        self._save_config()
        self._sync_buttons()

    def _selected_app_row(self) -> int:
        rows = self.apps_table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _add_app_manual(self) -> None:
        dialog = AddAppDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        package, label = dialog.values()
        if any(app.package == package for app in self.config.apps):
            QMessageBox.information(
                self, "Sudah ada", f"Paket '{package}' sudah ada di daftar."
            )
            return
        self.config.apps.append(
            AutomationApp(package=package, label=label, enabled=True)
        )
        self._persist()
        self._reload_apps_table()

    def _request_installed_apps(self) -> None:
        group = self.selected_group()
        if not group:
            QMessageBox.information(
                self, "Belum ada grup", "Pilih grup terlebih dahulu."
            )
            return
        self.loadAppsRequested.emit(group)

    def _edit_script(self) -> None:
        row = self._selected_app_row()
        if row < 0 or row >= len(self.config.apps):
            return
        app = self.config.apps[row]
        dialog = ScriptDialog(
            app,
            ref_width=self.config.reference_width,
            ref_height=self.config.reference_height,
            client=self.client,
            config=self.config,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        app.steps = list(dialog.result_steps)
        self._persist()
        self._reload_apps_table()
        self.apps_table.selectRow(row)

    def _remove_app(self) -> None:
        row = self._selected_app_row()
        if row < 0 or row >= len(self.config.apps):
            return
        app = self.config.apps[row]
        answer = QMessageBox.question(
            self, "Hapus Aplikasi", f"Hapus '{app.display_name}' dari daftar?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        del self.config.apps[row]
        self._persist()
        self._reload_apps_table()

    def _move_app(self, delta: int) -> None:
        row = self._selected_app_row()
        target = row + delta
        if row < 0 or not (0 <= target < len(self.config.apps)):
            return
        self.config.apps[row], self.config.apps[target] = (
            self.config.apps[target],
            self.config.apps[row],
        )
        self._persist()
        self._reload_apps_table()
        self.apps_table.selectRow(target)

    # --------------------------------------------------------------- signals
    def _sync_buttons(self) -> None:
        if self._running:
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            return
        has_group = self.selected_group() is not None
        has_app = bool(self.config.enabled_apps())
        self.start_button.setEnabled(has_group and has_app)
        self.stop_button.setEnabled(False)
        self.edit_script_button.setEnabled(bool(self.config.apps))
        self.remove_app_button.setEnabled(bool(self.config.apps))
        self.up_app_button.setEnabled(bool(self.config.apps))
        self.down_app_button.setEnabled(bool(self.config.apps))

    def _start(self) -> None:
        group = self.selected_group()
        if not group:
            QMessageBox.information(
                self, "Belum ada grup", "Pilih grup terlebih dahulu."
            )
            return
        config = self._collect_config()
        error = config.validation_error()
        if error:
            QMessageBox.warning(self, "Otomatisasi belum valid", error)
            return
        self.config = config
        self.store.save(config)
        self.startRequested.emit(group)

    def _stop(self) -> None:
        self.stop_button.setEnabled(False)
        self.status_label.setText("Menghentikan otomatisasi…")
        self.stopRequested.emit()

    def _load(self, settings: dict[str, str]) -> None:
        pass

    def collect(self) -> dict[str, str]:
        return {}
