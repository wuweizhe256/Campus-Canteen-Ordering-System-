from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from models.entities import SimulationConfig
from views.ui_widgets import dialog_stylesheet


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
        self.tables_spin.setEnabled(False)

        self.companion_ratio_spin = QSpinBox()
        self.companion_ratio_spin.setRange(0, 100)
        self.companion_ratio_spin.setValue(25)
        self.companion_ratio_spin.setSuffix(" %")

        self.two_tables_spin = QSpinBox()
        self.two_tables_spin.setRange(0, 36)
        self.two_tables_spin.setValue(6)
        self.two_tables_spin.setSuffix(" \u5f20")

        self.four_tables_spin = QSpinBox()
        self.four_tables_spin.setRange(0, 36)
        self.four_tables_spin.setValue(14)
        self.four_tables_spin.setSuffix(" \u5f20")

        self.six_tables_spin = QSpinBox()
        self.six_tables_spin.setRange(0, 36)
        self.six_tables_spin.setValue(4)
        self.six_tables_spin.setSuffix(" \u5f20")
        for spin in (self.two_tables_spin, self.four_tables_spin, self.six_tables_spin):
            spin.valueChanged.connect(self._update_table_count)

        self.total_students_spin = QSpinBox()
        self.total_students_spin.setRange(10, 100000)
        self.total_students_spin.setValue(120)
        self.total_students_spin.setSingleStep(50)
        self.total_students_spin.setSuffix(" \u4eba")

        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(0)
        self.seed_spin.setSpecialValueText("\u968f\u673a")

        basic_form = self._form_layout()
        basic_form.addRow("\u663e\u793a\u4eff\u771f\u65f6\u957f", self.minutes_spin)
        basic_form.addRow("\u7a97\u53e3\u6570\u91cf", self.stalls_spin)
        basic_form.addRow("\u751f\u6210\u5b66\u751f\u603b\u6570", self.total_students_spin)
        basic_form.addRow("\u968f\u673a\u79cd\u5b50", self.seed_spin)

        table_form = self._form_layout()
        table_type_row = QHBoxLayout()
        table_type_row.setSpacing(10)
        table_type_row.addWidget(self.two_tables_spin)
        table_type_row.addWidget(self.four_tables_spin)
        table_type_row.addWidget(self.six_tables_spin)
        table_form.addRow("2/4/6 \u4eba\u684c", table_type_row)
        table_form.addRow("\u9910\u684c\u603b\u6570", self.tables_spin)

        behavior_form = self._form_layout()
        behavior_form.addRow("\u540c\u884c\u6bd4\u4f8b", self.companion_ratio_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.setContentsMargins(20, 12, 20, 20)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("\u5f00\u59cb\u4eff\u771f")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("\u53d6\u6d88")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("DialogAcceptButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        content = QGridLayout()
        content.setContentsMargins(20, 20, 20, 8)
        content.setHorizontalSpacing(16)
        content.setVerticalSpacing(14)
        content.addWidget(self._group_box("\u57fa\u7840\u53c2\u6570", basic_form), 0, 0, 2, 1)
        content.addWidget(self._group_box("\u9910\u684c\u5e03\u5c40", table_form), 0, 1)
        content.addWidget(self._group_box("\u884c\u4e3a\u53c2\u6570", behavior_form), 1, 1)
        content.setColumnStretch(0, 1)
        content.setColumnStretch(1, 1)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(content)
        layout.addWidget(buttons)
        self.setLayout(layout)
        self._update_table_count()
        self._apply_style()
        self.setSizeGripEnabled(True)
        self.setMinimumSize(560, 360)
        self.resize(640, 420)

    def _form_layout(self) -> QFormLayout:
        form = QFormLayout()
        form.setContentsMargins(16, 20, 16, 16)
        form.setSpacing(14)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        return form

    def _group_box(self, title: str, form: QFormLayout) -> QGroupBox:
        group = QGroupBox(title)
        group.setLayout(form)
        return group

    def _update_table_count(self) -> None:
        self.tables_spin.setValue(
            self.two_tables_spin.value()
            + self.four_tables_spin.value()
            + self.six_tables_spin.value()
        )

    def config(self) -> SimulationConfig:
        seed = self.seed_spin.value()
        total_students = self.total_students_spin.value()
        companion_ratio = self.companion_ratio_spin.value() / 100.0
        typed_table_count = (
            self.two_tables_spin.value()
            + self.four_tables_spin.value()
            + self.six_tables_spin.value()
        )
        table_count = typed_table_count or self.tables_spin.value()
        return SimulationConfig(
            sim_minutes=self.minutes_spin.value(),
            stall_count=self.stalls_spin.value(),
            table_count=table_count,
            two_person_table_count=self.two_tables_spin.value(),
            four_person_table_count=self.four_tables_spin.value(),
            six_person_table_count=self.six_tables_spin.value(),
            companion_ratio=companion_ratio,
            companion_pair_ratio=companion_ratio * 0.7,
            companion_multi_ratio=companion_ratio * 0.3,
            seed=None if seed == 0 else seed,
            total_student_count=total_students,
            max_active_students=max(55, total_students),
        )

    def _apply_style(self) -> None:
        self.setStyleSheet(dialog_stylesheet())
