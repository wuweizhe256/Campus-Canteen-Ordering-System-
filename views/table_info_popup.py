from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from utils.fonts import ui_font
from views.ui_widgets import (
    DetailBadge,
    DetailTokens,
    detail_card_stylesheet,
    detail_progress_stylesheet,
    set_detail_value,
)


class TableInfoPopup(QDialog):
    """点击餐桌时弹出的占用、用餐进度和同行关系面板。"""

    def __init__(self, table: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._table = table
        self._table_id = int(_number(table.get("id"), 0) or 0)
        self._status_label: DetailBadge | None = None
        self._info_labels: dict[str, QLabel] = {}
        self._seats_scroll: QScrollArea | None = None
        self._companions_scroll: QScrollArea | None = None
        self._seat_widgets: dict[int, dict[str, Any]] = {}
        self._seats_signature: tuple[Any, ...] | None = None
        self._companions_signature: tuple[Any, ...] | None = None
        self._setup_ui()

    def table_id(self) -> int:
        return self._table_id

    def update_table(self, table: dict) -> None:
        self._table = table
        self._refresh_status()
        self._refresh_info()
        self._refresh_seats()
        self._refresh_companions()

    def _setup_ui(self) -> None:
        self.setWindowTitle(f"餐桌 {self._table_id + 1} 详情")
        self.setMinimumSize(340, 420)
        _apply_compact_dialog_size(self, 380, 560)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Dialog)

        root = QVBoxLayout()
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(f"餐桌 {self._table_id + 1}")
        title.setFont(ui_font(13, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {DetailTokens.TITLE_TEXT};")
        header.addWidget(title)
        header.addStretch()
        self._status_label = self._build_status_label()
        header.addWidget(self._status_label)
        root.addLayout(header)

        root.addWidget(_divider())
        root.addWidget(_section_title("占用情况"))
        root.addLayout(self._info_grid())

        root.addWidget(_divider())
        root.addWidget(_section_title("座位与用餐进度"))
        root.addWidget(self._build_seats_scroll(), 2)

        root.addWidget(_divider())
        root.addWidget(_section_title("同行关系"))
        root.addWidget(self._build_companions_scroll(), 1)

        self.setLayout(root)

    def _build_status_label(self) -> DetailBadge:
        label = DetailBadge()
        label.setFont(ui_font(11, QFont.Weight.Bold))
        self._apply_status_label(label)
        return label

    def _info_grid(self) -> QGridLayout:
        layout = QGridLayout()
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(4)

        self._info_labels["table_type"] = _info_value_label(self._table_type_display())
        _add_info_grid_row(layout, 0, 0, "餐桌类型", self._info_labels["table_type"])
        self._info_labels["seats"] = _info_value_label(str(self._seat_count()))
        _add_info_grid_row(layout, 1, 0, "座位数", self._info_labels["seats"])
        self._info_labels["occupied"] = _info_value_label(self._occupied_display())
        _add_info_grid_row(layout, 0, 2, "已占用", self._info_labels["occupied"])
        self._info_labels["reserved"] = _info_value_label(self._reserved_display())
        _add_info_grid_row(layout, 1, 2, "预占座", self._info_labels["reserved"])
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 1)
        return layout

    def _refresh_status(self) -> None:
        if self._status_label is not None:
            self._apply_status_label(self._status_label)

    def _refresh_info(self) -> None:
        if "table_type" in self._info_labels:
            set_detail_value(self._info_labels["table_type"], self._table_type_display())
        if "seats" in self._info_labels:
            set_detail_value(self._info_labels["seats"], str(self._seat_count()))
        if "occupied" in self._info_labels:
            set_detail_value(self._info_labels["occupied"], self._occupied_display())
        if "reserved" in self._info_labels:
            set_detail_value(self._info_labels["reserved"], self._reserved_display())

    def _refresh_seats(self) -> None:
        if self._seats_scroll is None:
            return
        signature = self._seat_signature()
        if signature == self._seats_signature:
            self._update_seat_widgets()
            return
        _set_scroll_widget_preserving_position(self._seats_scroll, self._seats_content())

    def _refresh_companions(self) -> None:
        if self._companions_scroll is None:
            return
        self._companions_scroll.setMaximumHeight(self._companions_height())
        signature = self._companion_signature()
        if signature == self._companions_signature:
            return
        _set_scroll_widget_preserving_position(self._companions_scroll, self._companions_content())

    def _build_seats_scroll(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        scroll.setWidget(self._seats_content())
        self._seats_scroll = scroll
        return scroll

    def _build_companions_scroll(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMaximumHeight(self._companions_height())
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        scroll.setWidget(self._companions_content())
        self._companions_scroll = scroll
        return scroll

    def _seats_content(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(DetailTokens.CARD_SPACING)
        self._seat_widgets = {}
        self._seats_signature = self._seat_signature()

        seats = self._seat_frames()
        if not seats:
            layout.addWidget(_empty_label("暂无座位信息"))
        else:
            for seat in seats:
                layout.addWidget(self._seat_card(seat))
        layout.addStretch()
        container.setLayout(layout)
        return container

    def _companions_content(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(DetailTokens.CARD_SPACING)
        self._companions_signature = self._companion_signature()

        groups = self._companion_groups()
        if not groups:
            layout.addWidget(_empty_label("本桌暂无同行关系"))
        else:
            for group in groups:
                layout.addWidget(self._companion_card(group))
            layout.addStretch()
        container.setLayout(layout)
        return container

    def _seat_card(self, seat: dict) -> QWidget:
        card = QWidget()
        card.setObjectName("SeatCard")
        card.setStyleSheet(detail_card_stylesheet("SeatCard"))
        layout = QVBoxLayout()
        layout.setContentsMargins(9, 7, 9, 7)
        layout.setSpacing(4)

        seat_index = int(_number(seat.get("index"), 0) or 0)
        status = str(seat.get("status") or "free")
        student = seat.get("student") if isinstance(seat.get("student"), dict) else None
        student_id = seat.get("student_id")
        widgets: dict[str, Any] = {}

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        seat_title = f"座位 {seat_index + 1}"
        if student is not None:
            seat_title = f"{seat_title} · S{student.get('id')}"
        elif student_id is not None:
            seat_title = f"{seat_title} · S{student_id}"
        seat_label = QLabel(seat_title)
        seat_label.setFont(ui_font(10, QFont.Weight.Bold))
        seat_label.setStyleSheet(f"color: {DetailTokens.TITLE_TEXT};")
        top_row.addWidget(seat_label)
        top_row.addStretch()
        status_badge = self._status_badge(status)
        widgets["status_badge"] = status_badge
        top_row.addWidget(status_badge)
        layout.addLayout(top_row)

        if student is None:
            card.setLayout(layout)
            self._seat_widgets[seat_index] = widgets
            return card

        state = _state_name(str(student.get("state") or ""))
        group_id = student.get("group_id")
        group_text = f" · G{group_id}" if group_id is not None else ""
        student_label = _small_label(f"{state}{group_text}")
        widgets["student_label"] = student_label
        top_row.insertWidget(1, student_label, 1)

        companion_ids = [
            item
            for item in student.get("companion_ids", [])
            if item is not None
        ] if isinstance(student.get("companion_ids"), list) else []
        if companion_ids:
            companion_label = _tiny_label(f"同行：{_student_list(companion_ids)}")
            widgets["companion_label"] = companion_label
            layout.addWidget(companion_label)

        progress = _number(student.get("eating_progress"), None)
        if progress is None:
            hint = "等待开始用餐" if status == "reserved" else "暂未进入用餐计时"
            hint_label = _tiny_label(hint)
            widgets["hint_label"] = hint_label
            layout.addWidget(hint_label)
        else:
            progress_row = QHBoxLayout()
            progress_row.setSpacing(6)
            progress_bar = _progress_bar(progress)
            widgets["progress_bar"] = progress_bar
            progress_row.addWidget(progress_bar, 1)
            progress_label = _tiny_label(_progress_text(progress))
            widgets["progress_label"] = progress_label
            progress_row.addWidget(progress_label)
            remaining = _format_seconds(student.get("eating_remaining"))
            time_label = _tiny_label(f"剩余 {remaining}")
            widgets["time_label"] = time_label
            progress_row.addWidget(time_label)
            layout.addLayout(progress_row)

        card.setLayout(layout)
        self._seat_widgets[seat_index] = widgets
        return card

    def _update_seat_widgets(self) -> None:
        for seat in self._seat_frames():
            seat_index = int(_number(seat.get("index"), 0) or 0)
            widgets = self._seat_widgets.get(seat_index)
            if not widgets:
                continue
            status = str(seat.get("status") or "free")
            status_badge = widgets.get("status_badge")
            if isinstance(status_badge, QLabel):
                _apply_status_badge(status_badge, status)

            student = seat.get("student") if isinstance(seat.get("student"), dict) else None
            if student is None:
                detail_label = widgets.get("detail_label")
                if isinstance(detail_label, QLabel):
                    student_id = seat.get("student_id")
                    detail_label.setText("空座" if student_id is None else f"学生 S{student_id}")
                continue

            student_label = widgets.get("student_label")
            if isinstance(student_label, QLabel):
                state = _state_name(str(student.get("state") or ""))
                group_id = student.get("group_id")
                group_text = f" · G{group_id}" if group_id is not None else ""
                student_label.setText(f"{state}{group_text}")

            companion_label = widgets.get("companion_label")
            companion_ids = [
                item
                for item in student.get("companion_ids", [])
                if item is not None
            ] if isinstance(student.get("companion_ids"), list) else []
            if isinstance(companion_label, QLabel):
                companion_label.setText(f"本桌同行：{_student_list(companion_ids)}")

            progress_bar = widgets.get("progress_bar")
            progress = _number(student.get("eating_progress"), None)
            if isinstance(progress_bar, QProgressBar) and progress is not None:
                _set_progress_bar_value(progress_bar, progress)
            progress_label = widgets.get("progress_label")
            if isinstance(progress_label, QLabel) and progress is not None:
                progress_label.setText(_progress_text(progress))

            time_label = widgets.get("time_label")
            if isinstance(time_label, QLabel):
                remaining = _format_seconds(student.get("eating_remaining"))
                time_label.setText(f"剩余 {remaining}")

    def _companion_card(self, group: dict) -> QWidget:
        card = QWidget()
        card.setObjectName("CompanionCard")
        card.setStyleSheet(detail_card_stylesheet("CompanionCard", bg=DetailTokens.CARD_ALT_BG))
        layout = QVBoxLayout()
        layout.setContentsMargins(9, 7, 9, 7)
        layout.setSpacing(4)

        group_id = group.get("group_id")
        group_size = int(_number(group.get("group_size"), 0) or 0)
        member_ids = [
            member_id
            for member_id in group.get("member_ids", [])
            if member_id is not None
        ] if isinstance(group.get("member_ids"), list) else []

        title = QLabel(f"同行组 G{group_id}")
        title.setFont(ui_font(10, QFont.Weight.Bold))
        title.setStyleSheet("color: #115e59;")
        layout.addWidget(title)

        if len(member_ids) >= 2:
            relation = f"{_student_list(member_ids)} 是同行"
        else:
            relation = f"{_student_list(member_ids)} 的同行未在本桌"
        layout.addWidget(_small_label(relation))

        if group_size:
            layout.addWidget(_small_label(f"本桌 {len(member_ids)} / 全组 {group_size} 人"))

        card.setLayout(layout)
        return card

    def _apply_status_label(self, label: QLabel) -> None:
        total = self._seat_count()
        occupied = self._occupied_count()
        reserved = self._reserved_count()
        used = occupied + reserved
        if used <= 0:
            text, status = "空桌", "normal"
        elif used >= total:
            text, status = "满座", "occupied"
        else:
            text, status = "部分占用", "occupied"
        label.set_status(text, status)

    def _table_type_display(self) -> str:
        table_type = str(self._table.get("table_type") or "")
        names = {"two": "二人桌", "four": "四人桌", "six": "六人桌"}
        return names.get(table_type, f"{self._seat_count()}人桌")

    def _occupied_display(self) -> str:
        return f"{self._occupied_count()} / {self._seat_count()}"

    def _reserved_display(self) -> str:
        return f"{self._reserved_count()} / {self._seat_count()}"

    def _seat_count(self) -> int:
        return max(1, int(_number(self._table.get("seat_count"), len(self._seat_frames()) or 1) or 1))

    def _occupied_count(self) -> int:
        return int(_number(self._table.get("occupied_count"), self._table.get("occupied") or 0) or 0)

    def _reserved_count(self) -> int:
        return int(_number(self._table.get("reserved_count"), 0) or 0)

    def _seat_frames(self) -> list[dict]:
        raw = self._table.get("seat_frames")
        if isinstance(raw, list):
            return [seat for seat in raw if isinstance(seat, dict)]
        seats = self._table.get("seats")
        if isinstance(seats, list):
            return [
                {
                    "index": index,
                    "status": "occupied" if student_id is not None else "free",
                    "student_id": student_id,
                }
                for index, student_id in enumerate(seats)
            ]
        return []

    def _companion_groups(self) -> list[dict]:
        raw = self._table.get("companion_groups")
        if isinstance(raw, list):
            return [group for group in raw if isinstance(group, dict)]
        return []

    def _companions_height(self) -> int:
        return 28 if not self._companion_groups() else 96

    def _seat_signature(self) -> tuple[Any, ...]:
        signature = []
        for seat in self._seat_frames():
            student = seat.get("student") if isinstance(seat.get("student"), dict) else {}
            companion_ids = student.get("companion_ids", []) if isinstance(student, dict) else []
            signature.append(
                (
                    int(_number(seat.get("index"), 0) or 0),
                    str(seat.get("status") or "free"),
                    seat.get("student_id"),
                    student.get("id") if isinstance(student, dict) else None,
                    student.get("state") if isinstance(student, dict) else None,
                    student.get("group_id") if isinstance(student, dict) else None,
                    tuple(companion_ids) if isinstance(companion_ids, list) else (),
                    _number(student.get("eating_progress"), None) is not None if isinstance(student, dict) else False,
                )
            )
        return tuple(signature)

    def _companion_signature(self) -> tuple[Any, ...]:
        signature = []
        for group in self._companion_groups():
            member_ids = group.get("member_ids", [])
            signature.append(
                (
                    group.get("group_id"),
                    group.get("group_size"),
                    tuple(member_ids) if isinstance(member_ids, list) else (),
                )
            )
        return tuple(signature)

    @staticmethod
    def _status_badge(status: str) -> QLabel:
        label = DetailBadge()
        label.setFont(ui_font(9, QFont.Weight.Bold))
        label.setFixedHeight(24)
        label.setMinimumWidth(44)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _apply_status_badge(label, status)
        return label


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setFont(ui_font(10, QFont.Weight.Bold))
    label.setStyleSheet(f"color: {DetailTokens.TITLE_TEXT};")
    return label


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"color: {DetailTokens.DIVIDER};")
    return line


def _info_value_label(text: str) -> QLabel:
    val = QLabel(text)
    val.setFont(ui_font(9, QFont.Weight.Bold))
    set_detail_value(val, text)
    return val


def _add_info_grid_row(layout: QGridLayout, row: int, column: int, label: str, value_widget: QLabel) -> None:
    lbl = QLabel(label)
    lbl.setFont(ui_font(9))
    lbl.setFixedWidth(DetailTokens.LABEL_WIDTH)
    lbl.setStyleSheet(f"color: {DetailTokens.LABEL_TEXT};")
    layout.addWidget(lbl, row, column)
    layout.addWidget(value_widget, row, column + 1)


def _info_row_widget(label: str, value_widget: QLabel) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(DetailTokens.ROW_SPACING)
    lbl = QLabel(label)
    lbl.setFont(ui_font(9))
    lbl.setFixedWidth(DetailTokens.LABEL_WIDTH)
    lbl.setStyleSheet(f"color: {DetailTokens.LABEL_TEXT};")
    layout.addWidget(lbl)
    layout.addWidget(value_widget)
    layout.addStretch()
    row.setLayout(layout)
    return row


def _small_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setFont(ui_font(8))
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {DetailTokens.LABEL_TEXT};")
    return label


def _tiny_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setFont(ui_font(8))
    label.setStyleSheet(f"color: {DetailTokens.LABEL_TEXT};")
    return label


def _empty_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setFont(ui_font(8))
    label.setFixedHeight(22)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    label.setStyleSheet(f"color: {DetailTokens.EMPTY_TEXT}; padding: 2px 0;")
    return label


def _apply_status_badge(label: QLabel, status: str) -> None:
    text, status_key = {
        "free": ("空闲", "normal"),
        "reserved": ("预占", "waiting"),
        "occupied": ("占用", "occupied"),
    }.get(status, ("未知", "empty"))
    if isinstance(label, DetailBadge):
        label.set_status(text, status_key)
        return
    badge = DetailBadge(text, status_key)
    label.setText(badge.text())
    label.setStyleSheet(badge.styleSheet())


def _set_scroll_widget_preserving_position(scroll: QScrollArea, widget: QWidget) -> None:
    vertical = scroll.verticalScrollBar()
    horizontal = scroll.horizontalScrollBar()
    old_vertical = vertical.value()
    old_horizontal = horizontal.value()
    was_at_bottom = old_vertical >= vertical.maximum()

    scroll.setWidget(widget)

    def restore_position() -> None:
        new_vertical = scroll.verticalScrollBar()
        new_horizontal = scroll.horizontalScrollBar()
        target_vertical = new_vertical.maximum() if was_at_bottom else min(old_vertical, new_vertical.maximum())
        new_vertical.setValue(target_vertical)
        new_horizontal.setValue(min(old_horizontal, new_horizontal.maximum()))

    restore_position()
    QTimer.singleShot(0, restore_position)


def _progress_bar(progress: float) -> QProgressBar:
    progress = max(0.0, min(1.0, progress))
    bar = QProgressBar()
    bar.setRange(0, 1000)
    bar.setTextVisible(False)
    bar.setFixedHeight(7)
    bar.setStyleSheet(detail_progress_stylesheet("in_progress"))
    _set_progress_bar_value(bar, progress)
    return bar


def _set_progress_bar_value(bar: QProgressBar, progress: float) -> None:
    progress = max(0.0, min(1.0, progress))
    bar.setValue(int(progress * 1000))
    bar.setFormat("")


def _progress_text(progress: float) -> str:
    progress = max(0.0, min(1.0, progress))
    return f"{progress * 100:.0f}%"


def _apply_compact_dialog_size(dialog: QDialog, width: int, height: int) -> None:
    screen = QApplication.primaryScreen()
    max_height = height
    if screen is not None:
        max_height = min(height, int(screen.availableGeometry().height() * 0.8))
    dialog.setMaximumSize(400, max_height)
    dialog.resize(min(width, 400), max_height)


def _state_name(state: str) -> str:
    names = {
        "deciding": "选择中",
        "moving_to_queue": "去排队",
        "queued": "排队中",
        "searching_seat": "找座中",
        "waiting_seat": "等座中",
        "moving_to_seat": "入座中",
        "eating": "用餐中",
        "moving_to_tray_return": "去回收",
        "leaving": "离场中",
        "done": "已离场",
    }
    return names.get(state, state or DetailTokens.EMPTY_DISPLAY)


def _student_list(student_ids: list[Any]) -> str:
    values = [f"S{student_id}" for student_id in student_ids if student_id is not None]
    return "、".join(values) if values else DetailTokens.EMPTY_DISPLAY


def _format_seconds(value: Any) -> str:
    seconds = _number(value, None)
    if seconds is None:
        return DetailTokens.EMPTY_DISPLAY
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    remaining = int(round(seconds % 60))
    if minutes <= 0:
        return f"{remaining}s"
    return f"{minutes}m {remaining:02d}s"


def _number(value: Any, default: float | None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
