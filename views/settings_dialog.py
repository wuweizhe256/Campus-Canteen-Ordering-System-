from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
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

    def __init__(
        self,
        parent: QWidget | None = None,
        current_font_size: int = 10,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.Tool, True)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 16)
        self.font_size_spin.setValue(current_font_size)
        self.font_size_spin.setSuffix(" pt")

        form = QFormLayout()
        form.setContentsMargins(16, 16, 16, 8)
        form.setSpacing(12)
        form.addRow("字体大小", self.font_size_spin)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Close
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setText("应用")
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        self.buttons.clicked.connect(self._button_clicked)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(form)
        layout.addWidget(self.buttons)
        self.setLayout(layout)
        self._apply_style()
        self.resize(260, 120)

    def _button_clicked(self, button) -> None:
        role = self.buttons.buttonRole(button)
        if role == QDialogButtonBox.ButtonRole.ApplyRole:
            self.settingsApplied.emit(
                None,
                self.font_size_spin.value(),
            )
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
