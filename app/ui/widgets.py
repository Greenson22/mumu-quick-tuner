"""Widget dan tema bersama."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

THEME = """
* {
    font-family: "Segoe UI", "Segoe UI Variable", sans-serif;
    font-size: 10pt;
    color: #e6e9f0;
}
QMainWindow, QWidget#root {
    background: #14171f;
}
QFrame#card {
    background: #1c2130;
    border: 1px solid #2a3142;
    border-radius: 12px;
}
QLabel#appTitle {
    font-size: 20pt;
    font-weight: 700;
    color: #ffffff;
}
QLabel#appSubtitle {
    color: #8b93a7;
    font-size: 9.5pt;
}
QLabel#cardTitle {
    font-size: 11.5pt;
    font-weight: 600;
    color: #ffffff;
}
QLabel#cardHint, QLabel#hint {
    color: #8b93a7;
    font-size: 9pt;
}
QLabel#badge {
    border-radius: 9px;
    padding: 3px 10px;
    font-size: 9pt;
    font-weight: 600;
}
QLabel#badge[state="ok"] {
    background: #153a2a;
    color: #4ade80;
}
QLabel#badge[state="warn"] {
    background: #3a2f14;
    color: #fbbf24;
}
QLabel#badge[state="off"] {
    background: #2a3142;
    color: #9aa3b8;
}
QLabel#deviceName {
    font-size: 12pt;
    font-weight: 600;
    color: #ffffff;
}
QTabWidget::pane {
    border: none;
    background: transparent;
}
QTabBar::tab {
    background: transparent;
    color: #8b93a7;
    padding: 9px 18px;
    margin-right: 4px;
    border-radius: 8px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: #232a3b;
    color: #ffffff;
}
QTabBar::tab:hover:!selected {
    color: #c7ccda;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background: #111520;
    border: 1px solid #2a3142;
    border-radius: 8px;
    padding: 7px 10px;
    min-height: 20px;
    selection-background-color: #3b82f6;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {
    border-color: #3a4358;
}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
    border-color: #3b82f6;
}
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled {
    color: #5b6478;
    background: #171b26;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 0;
    border: none;
}
QComboBox QAbstractItemView {
    background: #1c2130;
    border: 1px solid #2a3142;
    selection-background-color: #2f3b55;
    outline: none;
    padding: 4px;
}
QCheckBox {
    spacing: 10px;
}
QCheckBox::indicator {
    width: 40px;
    height: 22px;
    border-radius: 11px;
    background: #2a3142;
    border: 1px solid #3a4358;
}
QCheckBox::indicator:checked {
    background: #2563eb;
    border-color: #2563eb;
    image: none;
}
QCheckBox::indicator:disabled {
    background: #1a1f2b;
    border-color: #262d3d;
}
QPushButton {
    background: #232a3b;
    border: 1px solid #2f374a;
    border-radius: 9px;
    padding: 9px 18px;
    font-weight: 600;
}
QPushButton:hover {
    background: #2b3346;
}
QPushButton:pressed {
    background: #1d2433;
}
QPushButton:disabled {
    color: #5b6478;
    background: #191e29;
    border-color: #232a3b;
}
QPushButton#primary {
    background: #2563eb;
    border-color: #2563eb;
    color: #ffffff;
}
QPushButton#primary:hover {
    background: #3b82f6;
}
QPushButton#primary:disabled {
    background: #1f2c4a;
    border-color: #1f2c4a;
    color: #6b7a99;
}
QPushButton#danger {
    background: #3a1f24;
    border-color: #5a2d35;
    color: #fca5a5;
}
QPushButton#danger:hover {
    background: #4a262d;
}
QPushButton#danger:disabled {
    background: #191e29;
    border-color: #232a3b;
    color: #5b6478;
}
QListWidget {
    background: #111520;
    border: 1px solid #2a3142;
    border-radius: 10px;
    padding: 6px;
    outline: none;
}
QListWidget::item {
    padding: 9px 10px;
    border-radius: 7px;
}
QListWidget::item:selected {
    background: #2f3b55;
    color: #ffffff;
}
QListWidget::item:hover:!selected {
    background: #1d2433;
}
QTableWidget {
    background: #111520;
    alternate-background-color: #161b27;
    border: 1px solid #2a3142;
    border-radius: 10px;
    gridline-color: #232a3b;
    outline: none;
    selection-background-color: #2f3b55;
    selection-color: #ffffff;
}
QTableWidget::item {
    padding: 6px 8px;
}
QTableWidget::item:selected {
    background: #2f3b55;
    color: #ffffff;
}
QHeaderView::section {
    background: #1c2130;
    color: #8b93a7;
    border: none;
    border-bottom: 1px solid #2a3142;
    padding: 7px 8px;
    font-weight: 600;
}
QTableCornerButton::section {
    background: #1c2130;
    border: none;
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QAbstractScrollArea::corner {
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #2f374a;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #3d4760;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QStatusBar {
    background: #14171f;
    color: #8b93a7;
}
QDialog {
    background: #14171f;
    color: #e6e9f0;
}
QDialog QLabel {
    color: #e6e9f0;
}
QDialog QLabel#hint {
    color: #8b93a7;
}
QDialog QDialogButtonBox QPushButton {
    min-width: 80px;
}
QLineEdit {
    color: #e6e9f0;
}
QLineEdit::placeholder {
    color: #6b7280;
}
QMessageBox {
    background: #1c2130;
}
QToolTip {
    background: #232a3b;
    color: #e6e9f0;
    border: 1px solid #2f374a;
    padding: 5px;
}
"""


class Card(QFrame):
    """Kartu dengan judul dan area isi (QFormLayout)."""

    def __init__(self, title: str, hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        outer.addWidget(heading)

        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("cardHint")
            hint_label.setWordWrap(True)
            outer.addWidget(hint_label)

        self.form = QFormLayout()
        self.form.setContentsMargins(0, 2, 0, 0)
        self.form.setHorizontalSpacing(24)
        self.form.setVerticalSpacing(12)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        outer.addLayout(self.form)

    def add_row(self, label: str, widget: QWidget, hint: str = "") -> None:
        holder = QWidget()
        box = QVBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(3)
        box.addWidget(widget)
        if hint:
            note = QLabel(hint)
            note.setObjectName("hint")
            note.setWordWrap(True)
            box.addWidget(note)
        self.form.addRow(label, holder)


def separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: #2a3142;")
    return line


def checkbox(text: str = "") -> QCheckBox:
    box = QCheckBox(text)
    box.setCursor(Qt.CursorShape.PointingHandCursor)
    return box
