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
        self.setWindowTitle("\u4eff\u771f\u914d\u7f6e")
        self.setModal(True)

        self.minutes_spin = QSpinBox()
        self.minutes_spin.setRange(30, 60)
        self.minutes_spin.setValue(30)
        self.minutes_spin.setSuffix(" \u5206\u949f")

        self.stalls_spin = QSpinBox()
        self.stalls_spin.setRange(1, 20)
        self.stalls_spin.setValue(10)
        self.stalls_spin.setSuffix(" \u4e2a")

        self.tables_spin = QSpinBox()
        self.tables_spin.setRange(6, 36)
        self.tables_spin.setValue(24)
        self.tables_spin.setSuffix(" \u5f20")

        self.total_students_spin = QSpinBox()
        self.total_students_spin.setRange(10, 100000)
        self.total_students_spin.setValue(120)
        self.total_students_spin.setSingleStep(50)
        self.total_students_spin.setSuffix(" \u4eba")

        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(0)
        self.seed_spin.setSpecialValueText("\u968f\u673a")

        form = QFormLayout()
        form.addRow("\u663e\u793a\u4eff\u771f\u65f6\u957f", self.minutes_spin)
        form.addRow("\u7a97\u53e3\u6570\u91cf", self.stalls_spin)
        form.addRow("\u9910\u684c\u6570\u91cf", self.tables_spin)
        form.addRow("\u751f\u6210\u5b66\u751f\u603b\u6570", self.total_students_spin)
        form.addRow("\u968f\u673a\u79cd\u5b50", self.seed_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)
        self.resize(360, 230)

    def config(self) -> SimulationConfig:
        seed = self.seed_spin.value()
        total_students = self.total_students_spin.value()
        return SimulationConfig(
            sim_minutes=self.minutes_spin.value(),
            stall_count=self.stalls_spin.value(),
            table_count=self.tables_spin.value(),
            seed=None if seed == 0 else seed,
            total_student_count=total_students,
            max_active_students=max(55, total_students),
        )
