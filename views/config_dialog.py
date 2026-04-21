from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from models.entities import SimulationConfig


class ConfigDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("仿真配置")
        self.setModal(True)

        self.minutes_spin = QSpinBox()
        self.minutes_spin.setRange(30, 60)
        self.minutes_spin.setValue(30)
        self.minutes_spin.setSuffix(" 分钟")

        self.stalls_spin = QSpinBox()
        self.stalls_spin.setRange(1, 20)
        self.stalls_spin.setValue(10)
        self.stalls_spin.setSuffix(" 个")

        self.tables_spin = QSpinBox()
        self.tables_spin.setRange(6, 36)
        self.tables_spin.setValue(24)
        self.tables_spin.setSuffix(" 张")

        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(0)
        self.seed_spin.setSpecialValueText("随机")

        form = QFormLayout()
        form.addRow("显示仿真时长", self.minutes_spin)
        form.addRow("窗口数量", self.stalls_spin)
        form.addRow("餐桌数量", self.tables_spin)
        form.addRow("随机种子", self.seed_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)
        self.resize(340, 190)

    def config(self) -> SimulationConfig:
        seed = self.seed_spin.value()
        return SimulationConfig(
            sim_minutes=self.minutes_spin.value(),
            stall_count=self.stalls_spin.value(),
            table_count=self.tables_spin.value(),
            seed=None if seed == 0 else seed,
        )
