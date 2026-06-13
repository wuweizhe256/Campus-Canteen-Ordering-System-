from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
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
    detail_progress_stylesheet,
    set_detail_value,
)


class StudentInfoPopup(QDialog):
    """点击学生时弹出的实时状态与寻路信息面板。"""

    def __init__(self, student: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._student: dict | None = student
        self._student_id = int(_number(student.get("id"), 0) or 0)
        self._title_label: QLabel | None = None
        self._status_label: DetailBadge | None = None
        self._labels: dict[str, QLabel] = {}
        self._path_progress: QProgressBar | None = None
        self._eating_progress: QProgressBar | None = None
        self._setup_ui()
        self.update_student(student)

    def student_id(self) -> int:
        return self._student_id

    def update_student(self, student: dict | None) -> None:
        self._student = student
        self._refresh_header()
        self._refresh_labels()

    def _setup_ui(self) -> None:
        self.setWindowTitle(f"学生 S{self._student_id} 详情")
        self.setMinimumSize(360, 420)
        self.resize(400, 520)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Dialog)
        self.setStyleSheet(
            """
            QDialog {
                background: #fffaf0;
            }
            QScrollArea {
                background: #fffaf0;
                border: 0;
            }
            QScrollArea > QWidget > QWidget {
                background: #fffaf0;
            }
            """
        )

        root = QVBoxLayout()
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)
        self._title_label = QLabel(f"学生 S{self._student_id}")
        self._title_label.setFont(ui_font(15, QFont.Weight.Bold))
        self._title_label.setStyleSheet("color: #4a3728;")
        header.addWidget(self._title_label)
        header.addStretch()
        self._status_label = DetailBadge()
        self._status_label.setFont(ui_font(11, QFont.Weight.Bold))
        header.addWidget(self._status_label)
        root.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        content = QWidget()
        content.setObjectName("PopupContent")
        content.setStyleSheet("QWidget#PopupContent { background: #fffaf0; }")
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 12, 0)
        content_layout.setSpacing(10)

        content_layout.addWidget(_divider())
        content_layout.addWidget(_section_title("当前状态"))
        status_box = QVBoxLayout()
        status_box.setSpacing(6)
        for key, label in (
            ("state", "状态"),
            ("time_in_system", "在场时间"),
            ("position", "当前位置"),
            ("target", "目标位置"),
            ("speed", "移动速度"),
        ):
            self._labels[key] = _value_label()
            status_box.addWidget(_row_widget(label, self._labels[key]))
        content_layout.addLayout(status_box)

        content_layout.addWidget(_divider())
        content_layout.addWidget(_section_title("寻路状态"))
        path_box = QVBoxLayout()
        path_box.setSpacing(6)
        for key, label in (
            ("path_status", "路径状态"),
            ("path_id", "路径编号"),
            ("path_waypoints", "剩余路点"),
            ("path_distance", "剩余距离"),
            ("path_duration", "已走时间"),
            ("stuck", "卡顿/重规划"),
        ):
            self._labels[key] = _value_label()
            path_box.addWidget(_row_widget(label, self._labels[key]))
        self._path_progress = _progress_bar()
        path_box.addWidget(self._path_progress)
        content_layout.addLayout(path_box)

        content_layout.addWidget(_divider())
        content_layout.addWidget(_section_title("业务信息"))
        business_box = QVBoxLayout()
        business_box.setSpacing(6)
        for key, label in (
            ("stall", "窗口/队列"),
            ("table", "餐桌/座位"),
            ("order", "订单/菜品"),
            ("group", "同行关系"),
            ("door", "入口/出口"),
            ("preferences", "偏好"),
        ):
            self._labels[key] = _value_label()
            business_box.addWidget(_row_widget(label, self._labels[key]))
        content_layout.addLayout(business_box)

        content_layout.addWidget(_divider())
        content_layout.addWidget(_section_title("用餐进度"))
        self._labels["eating"] = _value_label()
        content_layout.addWidget(_row_widget("用餐计时", self._labels["eating"]))
        self._eating_progress = _progress_bar()
        content_layout.addWidget(self._eating_progress)
        content_layout.addStretch()

        content.setLayout(content_layout)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self.setLayout(root)

    def _refresh_header(self) -> None:
        student = self._student
        if self._title_label is not None:
            self._title_label.setText(f"学生 S{self._student_id}")
        if self._status_label is None:
            return
        if student is None:
            self._status_label.set_status("已离场", "empty")
            return
        state = str(student.get("state") or "")
        label, status = _state_badge(state)
        self._status_label.set_status(label, status)

    def _refresh_labels(self) -> None:
        student = self._student
        if student is None:
            for label in self._labels.values():
                set_detail_value(label, None)
            _set_progress(self._path_progress, None)
            _set_progress(self._eating_progress, None)
            if "state" in self._labels:
                set_detail_value(self._labels["state"], "已离场")
            return

        self._set("state", _state_name(str(student.get("state") or "")))
        self._set("time_in_system", _format_seconds(student.get("time_in_system")))
        self._set("position", _point_text(student.get("x"), student.get("y")))
        self._set("target", _point_text(student.get("target_x"), student.get("target_y")))
        self._set("speed", f"{_format_decimal(student.get('actual_speed'))} px/s")

        self._set("path_status", _path_status_name(str(student.get("path_status") or "")))
        self._set("path_id", _display(student.get("path_id")))
        self._set("path_waypoints", _display(student.get("path_waypoint_count")))
        self._set("path_distance", _format_distance(student.get("path_remaining_distance")))
        self._set("path_duration", _format_seconds(student.get("path_duration")))
        self._set(
            "stuck",
            f"{_format_seconds(student.get('stuck_time'))} / {_display(student.get('reroute_count'))} 次",
        )
        _set_progress(
            self._path_progress,
            _number(student.get("path_progress"), None),
            _progress_status_key(str(student.get("state") or ""), str(student.get("path_status") or "")),
        )

        stall = _indexed("窗口", student.get("stall_id"))
        queue_position = student.get("queue_position")
        queue_text = f"队列第 {queue_position} 位" if queue_position is not None else "未排队"
        self._set("stall", f"{stall}，{queue_text}")

        table = _indexed("餐桌", student.get("table_id"))
        seat = _indexed("座位", student.get("seat_index"), offset=1)
        self._set("table", f"{table}，{seat}")

        dish_name = student.get("dish_name")
        dish = f"{dish_name} (#{student.get('dish_id')})" if dish_name else _display(student.get("dish_id"))
        self._set("order", f"订单 {_display(student.get('order_id'))}，菜品 {dish}")

        group_id = student.get("group_id")
        group_size = student.get("group_size")
        group_text = (
            "无同行"
            if group_id is None
            else f"同行组 G{group_id}，共 {group_size or DetailTokens.EMPTY_DISPLAY} 人"
        )
        self._set("group", group_text)
        self._set(
            "door",
            f"{_indexed('入口', student.get('entrance_id'))}，{_indexed('出口', student.get('exit_id'))}",
        )
        self._set("preferences", _preferences_text(student.get("preferences")))

        eating_progress = _number(student.get("eating_progress"), None)
        if eating_progress is None:
            self._set("eating", "未进入用餐计时")
        else:
            self._set(
                "eating",
                f"已用餐 {_format_seconds(student.get('eating_elapsed'))}，剩余 {_format_seconds(student.get('eating_remaining'))}",
            )
        _set_progress(self._eating_progress, eating_progress, "in_progress")

    def _set(self, key: str, text: str) -> None:
        label = self._labels.get(key)
        if label is not None:
            set_detail_value(label, text)


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setFont(ui_font(11, QFont.Weight.Bold))
    label.setStyleSheet("color: #5c4a3a;")
    return label


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: #d2dfc9;")
    return line


def _value_label() -> QLabel:
    label = QLabel(DetailTokens.EMPTY_DISPLAY)
    label.setFont(ui_font(10, QFont.Weight.Bold))
    label.setWordWrap(True)
    set_detail_value(label, None)
    return label


def _row_widget(label: str, value_widget: QLabel) -> QWidget:
    row = QWidget()
    row.setMinimumHeight(28)
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    key = QLabel(label)
    key.setFont(ui_font(10))
    key.setFixedWidth(92)
    key.setStyleSheet("color: #78716c;")
    layout.addWidget(key)
    layout.addWidget(value_widget, 1)
    row.setLayout(layout)
    return row


def _progress_bar() -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, 1000)
    bar.setTextVisible(True)
    bar.setFixedHeight(10)
    bar.setStyleSheet(detail_progress_stylesheet("in_progress"))
    _set_progress(bar, None)
    return bar


def _set_progress(bar: QProgressBar | None, progress: float | None, status: str = "in_progress") -> None:
    if bar is None:
        return
    if progress is None:
        bar.setValue(0)
        bar.setFormat("")
        bar.setVisible(False)
        return
    progress = max(0.0, min(1.0, progress))
    bar.setVisible(True)
    bar.setStyleSheet(detail_progress_stylesheet(status))
    bar.setValue(int(progress * 1000))
    bar.setFormat(f"{progress * 100:.0f}%")


def _state_badge(state: str) -> tuple[str, str]:
    if state == "eating":
        return "用餐中", "in_progress"
    if state in {"moving_to_queue", "moving_to_seat", "moving_to_tray_return", "leaving"}:
        return "移动中", "in_progress"
    if state in {"queued", "waiting_seat"}:
        return "等待中", "waiting"
    if state == "searching_seat":
        return "找座中", "normal"
    if state == "deciding":
        return "选择中", "normal"
    return _state_name(state), "empty"


def _progress_status_key(state: str, path_status: str) -> str:
    if state in {"queued", "waiting_seat"}:
        return "waiting"
    if path_status in {"active", "pending", "direct"}:
        return "in_progress"
    if path_status == "idle":
        return "empty"
    return "normal"


def _state_name(state: str) -> str:
    names = {
        "deciding": "选择菜品中",
        "moving_to_queue": "前往窗口",
        "queued": "排队取餐",
        "searching_seat": "寻找座位",
        "waiting_seat": "等待空座",
        "moving_to_seat": "前往座位",
        "eating": "用餐中",
        "moving_to_tray_return": "前往回收口",
        "leaving": "离场中",
        "done": "已离场",
    }
    return names.get(state, state or DetailTokens.EMPTY_DISPLAY)


def _path_status_name(status: str) -> str:
    names = {
        "active": "导航路径中",
        "pending": "沿路点移动",
        "direct": "直接朝目标移动",
        "idle": "无活动路径",
    }
    return names.get(status, status or DetailTokens.EMPTY_DISPLAY)


def _preferences_text(value: Any) -> str:
    if not isinstance(value, dict):
        return DetailTokens.EMPTY_DISPLAY
    labels = {
        "meat": "荤",
        "veg": "素",
        "price_sensitivity": "价格",
        "wait_tolerance": "耐等",
        "spicy": "辣",
    }
    parts = []
    for key in ("meat", "veg", "spicy", "price_sensitivity", "wait_tolerance"):
        number = _number(value.get(key), None)
        if number is not None:
            parts.append(f"{labels.get(key, key)} {number:.2f}")
    return "，".join(parts) if parts else DetailTokens.EMPTY_DISPLAY


def _indexed(label: str, value: Any, offset: int = 1) -> str:
    number = _number(value, None)
    if number is None:
        return f"{label} {DetailTokens.EMPTY_DISPLAY}"
    return f"{label} {int(number) + offset}"


def _point_text(x_value: Any, y_value: Any) -> str:
    x = _number(x_value, None)
    y = _number(y_value, None)
    if x is None or y is None:
        return DetailTokens.EMPTY_DISPLAY
    return f"({x:.1f}, {y:.1f})"


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


def _format_decimal(value: Any) -> str:
    number = _number(value, None)
    if number is None:
        return DetailTokens.EMPTY_DISPLAY
    return f"{number:.1f}"


def _format_distance(value: Any) -> str:
    number = _number(value, None)
    if number is None:
        return DetailTokens.EMPTY_DISPLAY
    return f"{number:.1f} px"


def _display(value: Any) -> str:
    return DetailTokens.EMPTY_DISPLAY if value is None else str(value)


def _number(value: Any, default: float | None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
