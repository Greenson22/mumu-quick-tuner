"""Bagian-bagian tab pengaturan."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app import models
from app.services.profiles import ProfileStore
from app.ui.widgets import Card, checkbox


class ScrollSection(QScrollArea):
    """Base tab yang bisa di-scroll."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)

        self._body = QWidget()
        self._body.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(2, 2, 10, 10)
        self._layout.setSpacing(14)
        self._layout.addStretch(1)
        self.setWidget(self._body)

        self.settings: dict[str, str] = {}

    def add_card(self, card: Card) -> None:
        self._layout.insertWidget(self._layout.count() - 1, card)

    def load(self, settings: dict[str, str]) -> None:
        self.settings = dict(settings)
        self._load(settings)

    def _load(self, settings: dict[str, str]) -> None:  # pragma: no cover
        raise NotImplementedError

    def collect(self) -> dict[str, str]:  # pragma: no cover
        raise NotImplementedError


def _float_str(value: float) -> str:
    return f"{value:.6f}"


class TampilanSection(ScrollSection):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # ---------------------------------------------------------- resolusi
        resolution = Card(
            "Resolusi",
            "Pilih preset atau tentukan ukuran sendiri. Perubahan diterapkan "
            "saat device berhenti.",
        )

        self.mode = QComboBox()
        self.mode.setMinimumWidth(360)
        resolution.add_row("Mode resolusi", self.mode)

        self.width = QSpinBox()
        self.width.setRange(380, 4096)
        self.width.setMinimumWidth(360)
        self.width.setSuffix(" px")
        self.height = QSpinBox()
        self.height.setRange(380, 4096)
        self.height.setMinimumWidth(360)
        self.height.setSuffix(" px")
        self.dpi = QSpinBox()
        self.dpi.setRange(10, 960)
        self.dpi.setMinimumWidth(360)
        self.dpi.setSuffix(" dpi")

        self.width.setEnabled(False)
        self.height.setEnabled(False)
        self.dpi.setEnabled(False)

        resolution.add_row("Lebar (custom)", self.width)
        resolution.add_row("Tinggi (custom)", self.height)
        resolution.add_row("DPI (custom)", self.dpi)
        self.add_card(resolution)

        self.mode.currentIndexChanged.connect(self._mode_changed)

        # --------------------------------------------------------------- fps
        frame = Card(
            "Frame rate",
            "FPS tinggi meningkatkan kelancaran tetapi membebani CPU/GPU. "
            "Perubahan diterapkan setelah device dimatikan.",
        )

        self.max_fps = QComboBox()
        self.max_fps.setEditable(True)
        self.max_fps.setMinimumWidth(360)
        self.max_fps.lineEdit().setValidator(QIntValidator(1, 480, self))
        for fps in (15, 20, 24, 30, 45, 60, 90, 120, 144, 165, 240, 480):
            self.max_fps.addItem(str(fps))
        frame.add_row("FPS maksimum", self.max_fps, "Rentang aman: 1–480 FPS.")

        self.dynamic_fps = checkbox("Sesuaikan FPS secara dinamis")
        frame.add_row("Dynamic FPS", self.dynamic_fps)

        self.min_fps = QComboBox()
        self.min_fps.setMinimumWidth(360)
        frame.add_row("Batas FPS terendah", self.min_fps)

        self.vsync = checkbox("Aktifkan vertical sync")
        frame.add_row("Vertical sync", self.vsync)

        self.show_fps = checkbox("Tampilkan penghitung FPS di layar")
        frame.add_row("Tampilkan FPS", self.show_fps)

        self.add_card(frame)

        self.dynamic_fps.toggled.connect(self.min_fps.setEnabled)

    def _mode_changed(self) -> None:
        custom = self.mode.currentData() == "custom"
        self.width.setEnabled(custom)
        self.height.setEnabled(custom)
        self.dpi.setEnabled(custom)

    def _load(self, settings: dict[str, str]) -> None:
        self.mode.blockSignals(True)
        self.mode.clear()

        for mode, title in models.RESOLUTION_MODE_NAMES.items():
            for index in range(4):
                width = settings.get(f"resolution_width.{mode}.{index}", "")
                height = settings.get(f"resolution_height.{mode}.{index}", "")
                dpi = settings.get(f"resolution_dpi.{mode}.{index}", "")
                if not width or not height or not dpi:
                    continue
                label = (
                    f"{title} {index + 1} — "
                    f"{models.format_number(width)}×{models.format_number(height)} "
                    f"@ {models.format_number(dpi)} dpi"
                )
                self.mode.addItem(label, f"{mode}.{index}")

        self.mode.addItem("Custom (atur sendiri)", "custom")

        current = settings.get("resolution_mode", "phone.3")
        position = self.mode.findData(current)
        self.mode.setCurrentIndex(position if position >= 0 else 0)
        self.mode.blockSignals(False)
        self._mode_changed()

        self.width.setValue(int(float(settings.get("resolution_width.custom", 540))))
        self.height.setValue(int(float(settings.get("resolution_height.custom", 960))))
        self.dpi.setValue(int(float(settings.get("resolution_dpi.custom", 240))))

        self.max_fps.setEditText(settings.get("max_frame_rate", "30"))

        self.min_fps.clear()
        for value in models.parse_number_list(
            settings.get("dynamic_low_frame_rate_limit.list", "[5,10,15,20,25,30,35,40,45,50,55,60]")
        ):
            self.min_fps.addItem(str(int(value)), str(int(value)))
        low = settings.get("dynamic_low_frame_rate_limit", "15")
        index = self.min_fps.findData(low)
        if index >= 0:
            self.min_fps.setCurrentIndex(index)

        self.dynamic_fps.setChecked(
            models.as_bool(settings.get("dynamic_adjust_frame_rate", "false"))
        )
        self.min_fps.setEnabled(self.dynamic_fps.isChecked())
        self.vsync.setChecked(models.as_bool(settings.get("vertical_sync", "false")))
        self.show_fps.setChecked(models.as_bool(settings.get("show_frame_rate", "false")))

    def collect(self) -> dict[str, str]:
        data: dict[str, str] = {
            "max_frame_rate": self._fps_value(),
            "dynamic_adjust_frame_rate": models.bool_str(self.dynamic_fps.isChecked()),
            "dynamic_low_frame_rate_limit": self.min_fps.currentData() or "15",
            "vertical_sync": models.bool_str(self.vsync.isChecked()),
            "show_frame_rate": models.bool_str(self.show_fps.isChecked()),
            "resolution_mode": self.mode.currentData() or "phone.3",
        }

        if self.mode.currentData() == "custom":
            data["resolution_width.custom"] = _float_str(float(self.width.value()))
            data["resolution_height.custom"] = _float_str(float(self.height.value()))
            data["resolution_dpi.custom"] = _float_str(float(self.dpi.value()))

        return data

    def _fps_value(self) -> str:
        raw = self.max_fps.currentText().strip()
        try:
            value = int(raw)
        except ValueError:
            value = int(self.settings.get("max_frame_rate", "30") or 30)
        value = max(1, min(480, value))
        return str(value)


class GrafisSection(ScrollSection):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        renderer = Card(
            "Renderer",
            "DirectX paling stabil. Vulkan biasanya lebih cepat tetapi "
            "bergantung pada driver GPU. Video memory: Performa = hemat "
            "memori GPU, Tampilan = kualitas lebih baik.",
        )
        self.renderer_mode = QComboBox()
        self.renderer_mode.setMinimumWidth(360)
        for key, label in models.RENDERER_NAMES.items():
            self.renderer_mode.addItem(label, key)
        renderer.add_row("API grafis", self.renderer_mode)

        self.renderer_strategy = QComboBox()
        self.renderer_strategy.setMinimumWidth(360)
        for key, label in models.RENDERER_STRATEGY_NAMES.items():
            self.renderer_strategy.addItem(label, key)
        renderer.add_row("Video memory strategy", self.renderer_strategy)
        self.add_card(renderer)

        gpu = Card(
            "GPU",
            "Model GPU memengaruhi profil yang dilaporkan ke game. "
            "Perubahan butuh restart device.",
        )
        self.gpu_mode = QComboBox()
        self.gpu_mode.setMinimumWidth(360)
        gpu.add_row("GPU model", self.gpu_mode)

        self.gpu_custom = QLineEdit()
        self.gpu_custom.setMinimumWidth(360)
        self.gpu_custom.setPlaceholderText("Contoh: Adreno (TM) 740")
        gpu.add_row("GPU model custom", self.gpu_custom)

        self.force_discrete = checkbox("Paksa memakai GPU dedicated")
        gpu.add_row("GPU dedicated", self.force_discrete)
        self.add_card(gpu)

        self.gpu_mode.currentIndexChanged.connect(self._gpu_changed)

    def _gpu_changed(self) -> None:
        self.gpu_custom.setEnabled(self.gpu_mode.currentData() == "custom")

    def _load(self, settings: dict[str, str]) -> None:
        self.renderer_mode.blockSignals(True)
        self.renderer_mode.setCurrentIndex(
            max(0, self.renderer_mode.findData(settings.get("renderer_mode", "dx")))
        )
        self.renderer_mode.blockSignals(False)

        self.renderer_strategy.blockSignals(True)
        self.renderer_strategy.setCurrentIndex(
            max(
                0,
                self.renderer_strategy.findData(
                    settings.get("renderer_strategy", "perf")
                ),
            )
        )
        self.renderer_strategy.blockSignals(False)

        self.gpu_mode.blockSignals(True)
        self.gpu_mode.clear()
        for key, label in models.GPU_MODE_NAMES.items():
            model = settings.get(f"gpu_model.{key}", "")
            text = f"{label} — {model}" if model else label
            self.gpu_mode.addItem(text, key)
        current = settings.get("gpu_mode", "middle")
        self.gpu_mode.setCurrentIndex(max(0, self.gpu_mode.findData(current)))
        self.gpu_mode.blockSignals(False)
        self._gpu_changed()

        self.gpu_custom.setText(settings.get("gpu_model.custom", ""))
        self.force_discrete.setChecked(
            models.as_bool(settings.get("force_discrete_graphics", "false"))
        )

    def collect(self) -> dict[str, str]:
        return {
            "renderer_mode": self.renderer_mode.currentData() or "dx",
            "renderer_strategy": self.renderer_strategy.currentData() or "perf",
            "gpu_mode": self.gpu_mode.currentData() or "middle",
            "gpu_model.custom": self.gpu_custom.text().strip(),
            "force_discrete_graphics": models.bool_str(self.force_discrete.isChecked()),
        }


class PerformaSection(ScrollSection):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        performance = Card(
            "CPU & RAM",
            "Nilai yang tersedia dibaca langsung dari MuMu. Perubahan pada "
            "bagian ini memerlukan restart device.",
        )

        self.mode = QComboBox()
        self.mode.setMinimumWidth(360)
        for key, label in models.PERFORMANCE_MODE_NAMES.items():
            self.mode.addItem(label, key)
        performance.add_row("Mode performa", self.mode)

        self.cpu = QComboBox()
        self.cpu.setMinimumWidth(360)
        performance.add_row("CPU core", self.cpu)

        self.memory = QComboBox()
        self.memory.setMinimumWidth(360)
        performance.add_row("RAM", self.memory)

        self.add_card(performance)

        self.summary = Card("Nilai aktif di VM")
        self.vm_summary = QLabel("-")
        self.vm_summary.setObjectName("hint")
        self.summary.form.addRow("CPU / RAM", self.vm_summary)
        self.add_card(self.summary)

        self.mode.currentIndexChanged.connect(self._mode_changed)

    def _mode_changed(self) -> None:
        custom = self.mode.currentData() == "custom"
        self.cpu.setEnabled(custom)
        self.memory.setEnabled(custom)

    def _load(self, settings: dict[str, str]) -> None:
        self.mode.blockSignals(True)
        self.mode.setCurrentIndex(
            max(0, self.mode.findData(settings.get("performance_mode", "custom")))
        )
        self.mode.blockSignals(False)
        self._mode_changed()

        self.cpu.clear()
        best_cpu = models.parse_best(settings.get("performance_cpu.list", ""))
        for value in models.parse_number_list(settings.get("performance_cpu.list", "")):
            number = int(value)
            label = f"{number} core"
            if best_cpu is not None and number == int(best_cpu):
                label += "  (disarankan)"
            self.cpu.addItem(label, str(number))
        current_cpu = settings.get("performance_cpu.custom", "1")
        index = self.cpu.findData(current_cpu)
        if index >= 0:
            self.cpu.setCurrentIndex(index)

        self.memory.clear()
        best_mem = models.parse_best(settings.get("performance_mem.list", ""))
        for value in models.parse_number_list(settings.get("performance_mem.list", "")):
            raw = f"{value:.6f}"
            label = models.format_ram(raw)
            if best_mem is not None and abs(value - best_mem) < 1e-9:
                label += "  (disarankan)"
            self.memory.addItem(label, raw)
        current_mem = settings.get("performance_mem.custom", "0.750000")
        index = self.memory.findData(current_mem)
        if index < 0:
            index = self.memory.findData(f"{float(current_mem):.6f}")
        if index >= 0:
            self.memory.setCurrentIndex(index)

        self.vm_summary.setText(
            f"{settings.get('vm_cpu', '?')} core / "
            f"{models.format_ram(settings.get('vm_mem', '?'))}"
        )

    def collect(self) -> dict[str, str]:
        return {
            "performance_mode": self.mode.currentData() or "custom",
            "performance_cpu.custom": self.cpu.currentData() or "1",
            "performance_mem.custom": self.memory.currentData() or "0.750000",
        }


class ProfilesSection(ScrollSection):
    loadRequested = pyqtSignal(object)
    applyRequested = pyqtSignal(object)
    saveRequested = pyqtSignal()
    deleteRequested = pyqtSignal(str)

    def __init__(
        self, store: ProfileStore, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.store = store

        card = Card(
            "Profil",
            "Preset bawaan dan profil simpanan. Profil hanya mengubah isi form; "
            "tekan Terapkan untuk mengirim ke device.",
        )

        self.list = QListWidget()
        self.list.setMinimumHeight(220)
        card.form.addRow(self.list)

        buttons = QHBoxLayout()
        self.load_button = QPushButton("Muat ke Form")
        self.apply_button = QPushButton("Terapkan Langsung")
        self.apply_button.setObjectName("primary")
        self.save_button = QPushButton("Simpan Form…")
        self.delete_button = QPushButton("Hapus")
        self.delete_button.setObjectName("danger")

        for button in (
            self.load_button,
            self.apply_button,
            self.save_button,
            self.delete_button,
        ):
            buttons.addWidget(button)
        card.form.addRow(buttons)

        self.add_card(card)

        self.load_button.clicked.connect(self._load_selected)
        self.apply_button.clicked.connect(self._apply_selected)
        self.save_button.clicked.connect(self.saveRequested.emit)
        self.delete_button.clicked.connect(self._delete_selected)
        self.list.itemSelectionChanged.connect(self._selection_changed)

        self.reload()

    def _load(self, settings: dict[str, str]) -> None:
        pass

    def collect(self) -> dict[str, str]:
        return {}

    def reload(self) -> None:
        selected = self.selected_name()
        self.list.clear()
        for name, changes, builtin in self.store.all_profiles():
            suffix = "" if builtin else "  (custom)"
            item = QListWidgetItem(name + suffix)
            item.setData(Qt.ItemDataRole.UserRole, (name, changes, builtin))
            self.list.addItem(item)
            if name == selected:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None and self.list.count() > 0:
            self.list.setCurrentRow(0)
        self._selection_changed()

    def selected(self) -> tuple[str, dict[str, str], bool] | None:
        item = self.list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def selected_name(self) -> str | None:
        data = self.selected()
        return data[0] if data else None

    def _selection_changed(self) -> None:
        data = self.selected()
        self.delete_button.setEnabled(data is not None and not data[2])
        enabled = data is not None
        self.load_button.setEnabled(enabled)
        self.apply_button.setEnabled(enabled)

    def _load_selected(self) -> None:
        data = self.selected()
        if data:
            self.loadRequested.emit(dict(data[1]))

    def _apply_selected(self) -> None:
        data = self.selected()
        if data:
            self.applyRequested.emit(dict(data[1]))

    def _delete_selected(self) -> None:
        data = self.selected()
        if data and not data[2]:
            self.deleteRequested.emit(data[0])
