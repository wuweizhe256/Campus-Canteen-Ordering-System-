from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from models.entities import SimulationConfig
from views.ui_widgets import dialog_stylesheet


class ConfigDialog(QDialog):
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
        current_resolution: tuple[int, int] = (1600, 920),
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("\u4eff\u771f\u914d\u7f6e")
        self.setModal(True)
        self._intro_animation: QPropertyAnimation | None = None
        self._resolutions = list(self.RESOLUTIONS)
        if current_resolution not in self._resolutions:
            self._resolutions.append(current_resolution)

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
        self.two_tables_spin.setObjectName("CompactSpinBox")
        self.two_tables_spin.setRange(0, 36)
        self.two_tables_spin.setValue(6)
        self.two_tables_spin.setSuffix(" \u5f20")

        self.four_tables_spin = QSpinBox()
        self.four_tables_spin.setObjectName("CompactSpinBox")
        self.four_tables_spin.setRange(0, 36)
        self.four_tables_spin.setValue(14)
        self.four_tables_spin.setSuffix(" \u5f20")

        self.six_tables_spin = QSpinBox()
        self.six_tables_spin.setObjectName("CompactSpinBox")
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
        self.resolution_group = QButtonGroup(self)
        self.resolution_widget = self._resolution_selector(current_resolution)

        for spin in (
            self.minutes_spin,
            self.stalls_spin,
            self.tables_spin,
            self.companion_ratio_spin,
            self.two_tables_spin,
            self.four_tables_spin,
            self.six_tables_spin,
            self.total_students_spin,
            self.seed_spin,
        ):
            spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)

        basic_form = self._form_layout()
        basic_form.addRow("\u663e\u793a\u4eff\u771f\u65f6\u957f", self.minutes_spin)
        basic_form.addRow("\u7a97\u53e3\u6570\u91cf", self.stalls_spin)
        basic_form.addRow("\u751f\u6210\u5b66\u751f\u603b\u6570", self.total_students_spin)
        basic_form.addRow("\u968f\u673a\u79cd\u5b50", self.seed_spin)
        basic_form.addRow("\u7a97\u53e3\u5206\u8fa8\u7387", self.resolution_widget)

        table_form = self._form_layout()
        table_type_row = QHBoxLayout()
        table_type_row.setSpacing(8)
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
        buttons.setCenterButtons(True)
        buttons.setContentsMargins(20, 8, 20, 18)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("\u5f00\u59cb\u4eff\u771f")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("\u53d6\u6d88")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("DialogAcceptButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        content = QGridLayout()
        content.setContentsMargins(22, 20, 22, 6)
        content.setHorizontalSpacing(16)
        content.setVerticalSpacing(14)
        content.addWidget(self._card("\u57fa\u7840\u53c2\u6570", basic_form), 0, 0, 2, 1)
        content.addWidget(self._card("\u9910\u684c\u5e03\u5c40", table_form), 0, 1)
        content.addWidget(self._card("\u884c\u4e3a\u53c2\u6570", behavior_form), 1, 1)
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
        self.setMinimumSize(660, 400)
        self.resize(700, 440)

    def _form_layout(self) -> QFormLayout:
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return form

    def _card(self, title: str, form: QFormLayout) -> QFrame:
        card = QFrame()
        card.setObjectName("ConfigCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(39, 31, 22, 18))
        card.setGraphicsEffect(shadow)

        title_label = QLabel(title)
        title_label.setObjectName("ConfigCardTitle")

        layout = QVBoxLayout()
        layout.setContentsMargins(18, 14, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(title_label)
        layout.addLayout(form)
        card.setLayout(layout)
        return card

    def _resolution_selector(self, current_resolution: tuple[int, int]) -> QWidget:
        widget = QWidget()
        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(6)
        checked_index = 0
        for index, resolution in enumerate(self._resolutions):
            width, height = resolution
            button = QRadioButton(f"{width} x {height}")
            button.setObjectName("ResolutionRadio")
            self.resolution_group.addButton(button, index)
            layout.addWidget(button, index // 3, index % 3)
            if resolution == current_resolution:
                checked_index = index
        selected_button = self.resolution_group.button(checked_index)
        if selected_button is not None:
            selected_button.setChecked(True)
        widget.setLayout(layout)
        return widget

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        QTimer.singleShot(0, self._play_intro_animation)

    def _play_intro_animation(self) -> None:
        end_pos = self.pos()
        self.move(end_pos + QPoint(0, 10))

        position = QPropertyAnimation(self, b"pos", self)
        position.setDuration(220)
        position.setStartValue(end_pos + QPoint(0, 10))
        position.setEndValue(end_pos)
        position.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._intro_animation = position
        self._intro_animation.start()

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

    def selected_resolution(self) -> tuple[int, int]:
        selected_id = self.resolution_group.checkedId()
        if 0 <= selected_id < len(self._resolutions):
            return self._resolutions[selected_id]
        return self._resolutions[0]

    def _apply_style(self) -> None:
        self.setStyleSheet(dialog_stylesheet())
