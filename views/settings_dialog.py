from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from utils.fonts import stylesheet_font_family


class SettingsDialog(QDialog):
    settingsApplied = pyqtSignal(object, int)

    RESOLUTIONS = (
        (1280, 720),
        (1366, 768),
        (1480, 860),
        (1600, 900),
        (1920, 1080),
    )

    def __init__(
        self,
        parent: QWidget | None = None,
        current_resolution: tuple[int, int] = (1480, 860),
        current_font_size: int = 10,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self._applied_resolution = current_resolution

        self.resolution_combo = QComboBox()
        resolutions = list(self.RESOLUTIONS)
        if current_resolution not in resolutions:
            resolutions.append(current_resolution)
        for width, height in resolutions:
            self.resolution_combo.addItem(f"{width} x {height}", (width, height))
        self._select_resolution(current_resolution)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 16)
        self.font_size_spin.setValue(current_font_size)
        self.font_size_spin.setSuffix(" pt")

        form = QFormLayout()
        form.setContentsMargins(16, 16, 16, 8)
        form.setSpacing(12)
        form.addRow("分辨率", self.resolution_combo)
        form.addRow("字体大小", self.font_size_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Close
        )
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText("应用")
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        buttons.clicked.connect(self._button_clicked)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)
        self._apply_style()
        self.resize(300, 150)

    def _select_resolution(self, resolution: tuple[int, int]) -> None:
        for index in range(self.resolution_combo.count()):
            if self.resolution_combo.itemData(index) == resolution:
                self.resolution_combo.setCurrentIndex(index)
                return

    def _button_clicked(self, button) -> None:
        role = self.sender().buttonRole(button)
        if role == QDialogButtonBox.ButtonRole.ApplyRole:
            current_resolution = self.resolution_combo.currentData()
            resolution = current_resolution if current_resolution != self._applied_resolution else None
            self.settingsApplied.emit(
                resolution,
                self.font_size_spin.value(),
            )
            if resolution is not None:
                self._applied_resolution = current_resolution
            return
        self.close()

    def _apply_style(self) -> None:
        font_family = stylesheet_font_family()
        style = """
            QDialog {
                background: #fff7ed;
                font-family: "Microsoft YaHei UI";
            }
            QLabel {
                color: #0f172a;
                font: 10pt "Microsoft YaHei UI";
            }
            QComboBox,
            QSpinBox {
                color: #0f172a;
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 6px 8px;
                font: 10pt "Microsoft YaHei UI";
            }
            QPushButton {
                color: #0f172a;
                background: #e2e8f0;
                border: 0;
                border-radius: 8px;
                padding: 7px 16px;
                min-width: 72px;
                font: 700 10pt "Microsoft YaHei UI";
            }
            QPushButton:hover {
                background: #cbd5e1;
            }
            """
        self.setStyleSheet(style.replace("Microsoft YaHei UI", font_family))
