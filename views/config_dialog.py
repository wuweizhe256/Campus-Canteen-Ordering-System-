from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
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
        self.tables_spin.setEnabled(False)

        self.dish_preference_weight_spin = QSpinBox()
        self.dish_preference_weight_spin.setRange(0, 100)
        self.dish_preference_weight_spin.setValue(40)
        self.dish_preference_weight_spin.setSuffix(" %")

        self.price_weight_spin = QSpinBox()
        self.price_weight_spin.setRange(0, 100)
        self.price_weight_spin.setValue(20)
        self.price_weight_spin.setSuffix(" %")

        self.default_dish_stock_spin = QSpinBox()
        self.default_dish_stock_spin.setRange(0, 9999)
        self.default_dish_stock_spin.setValue(24)
        self.default_dish_stock_spin.setSuffix(" \u4efd")

        self.low_stock_threshold_spin = QSpinBox()
        self.low_stock_threshold_spin.setRange(0, 999)
        self.low_stock_threshold_spin.setValue(3)
        self.low_stock_threshold_spin.setSuffix(" \u4efd")

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

        self.entrance_count_spin = QSpinBox()
        self.entrance_count_spin.setRange(1, 8)
        self.entrance_count_spin.setValue(1)
        self.entrance_count_spin.setSuffix(" \u4e2a")

        self.exit_count_spin = QSpinBox()
        self.exit_count_spin.setRange(1, 8)
        self.exit_count_spin.setValue(1)
        self.exit_count_spin.setSuffix(" \u4e2a")

        self.show_path_debug_checkbox = QCheckBox("\u9ed8\u8ba4\u663e\u793a\u8def\u5f84\u8c03\u8bd5\u5c42")
        self.show_obstacle_layer_checkbox = QCheckBox("\u9ed8\u8ba4\u663e\u793a\u969c\u788d\u7269\u5c42")

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
        form.addRow("\u9910\u684c\u603b\u6570", self.tables_spin)
        form.addRow("\u751f\u6210\u5b66\u751f\u603b\u6570", self.total_students_spin)
        form.addRow("\u968f\u673a\u79cd\u5b50", self.seed_spin)

        p1_form = QFormLayout()
        p1_form.addRow("\u83dc\u54c1\u504f\u597d\u6743\u91cd", self.dish_preference_weight_spin)
        p1_form.addRow("\u4ef7\u683c\u6743\u91cd", self.price_weight_spin)
        p1_form.addRow("\u9ed8\u8ba4\u83dc\u54c1\u5e93\u5b58", self.default_dish_stock_spin)
        p1_form.addRow("\u4f4e\u5e93\u5b58\u9608\u503c", self.low_stock_threshold_spin)
        p1_group = QGroupBox("P1 \u83dc\u54c1 / \u8ba2\u5355 / \u5e93\u5b58")
        p1_group.setLayout(p1_form)

        p2_form = QFormLayout()
        p2_form.addRow("\u540c\u884c\u6bd4\u4f8b", self.companion_ratio_spin)
        table_type_row = QHBoxLayout()
        table_type_row.addWidget(self.two_tables_spin)
        table_type_row.addWidget(self.four_tables_spin)
        table_type_row.addWidget(self.six_tables_spin)
        p2_form.addRow("2/4/6 \u4eba\u684c", table_type_row)
        p2_group = QGroupBox("P2 \u540c\u884c\u7ec4 / \u591a\u684c\u578b")
        p2_group.setLayout(p2_form)

        p3_form = QFormLayout()
        p3_form.addRow("\u5165\u53e3\u6570\u91cf", self.entrance_count_spin)
        p3_form.addRow("\u51fa\u53e3\u6570\u91cf", self.exit_count_spin)
        p3_form.addRow(self.show_path_debug_checkbox)
        p3_form.addRow(self.show_obstacle_layer_checkbox)
        p3_group = QGroupBox("P3 \u7a7a\u95f4 / \u8def\u5f84\u8c03\u8bd5")
        p3_group.setLayout(p3_form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(p1_group)
        layout.addWidget(p2_group)
        layout.addWidget(p3_group)
        layout.addWidget(buttons)
        self.setLayout(layout)
        self._update_table_count()
        self.resize(520, 560)

    def _update_table_count(self) -> None:
        self.tables_spin.setValue(
            self.two_tables_spin.value()
            + self.four_tables_spin.value()
            + self.six_tables_spin.value()
        )

    def config(self) -> SimulationConfig:
        seed = self.seed_spin.value()
        total_students = self.total_students_spin.value()
        return SimulationConfig(
            sim_minutes=self.minutes_spin.value(),
            stall_count=self.stalls_spin.value(),
            table_count=self.tables_spin.value(),
            dish_preference_weight=self.dish_preference_weight_spin.value() / 100.0,
            price_weight=self.price_weight_spin.value() / 100.0,
            default_dish_stock=self.default_dish_stock_spin.value(),
            low_stock_threshold=self.low_stock_threshold_spin.value(),
            companion_ratio=self.companion_ratio_spin.value() / 100.0,
            two_seat_table_count=self.two_tables_spin.value(),
            four_seat_table_count=self.four_tables_spin.value(),
            six_seat_table_count=self.six_tables_spin.value(),
            entrance_count=self.entrance_count_spin.value(),
            exit_count=self.exit_count_spin.value(),
            show_path_debug_layer=self.show_path_debug_checkbox.isChecked(),
            show_obstacle_layer=self.show_obstacle_layer_checkbox.isChecked(),
            seed=None if seed == 0 else seed,
            total_student_count=total_students,
            max_active_students=max(55, total_students),
        )
