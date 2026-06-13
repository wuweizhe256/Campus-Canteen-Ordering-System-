from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRectF, QSize, Qt, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from utils.fonts import stylesheet_font_family, ui_font


class StatsTokens:
    HEALTHY = "#36A37A"
    CAUTION = "#F0913C"
    ALERT = "#E23B3B"
    THEME = "#0f766e"
    MUTED = "#64748b"
    INK = "#0f172a"
    CARD_BG = "#f8fafc"
    TRACK = "#e5e7eb"
    HEAT_STOPS = (
        (0.00, "#36A37A"),
        (0.25, "#8CC152"),
        (0.50, "#F4C744"),
        (0.75, "#F0913C"),
        (1.00, "#E23B3B"),
    )
    GAUGE_THRESHOLDS = {
        "等待": {"caution": 60.0, "alert": 120.0},
        "座位": {"low_caution": 0.18, "caution": 0.72, "alert": 0.90},
        "人数": {"caution": 70.0, "alert": 100.0},
        "拥堵": {"caution": 0.55, "alert": 0.80},
        "卡住": {"caution": 3.0, "alert": 8.0},
    }
    TABLE_UTILIZATION_THRESHOLDS = {"caution": 0.85, "alert": 0.95}


class StatsPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(340)
        self.setMaximumWidth(460)
        self.setObjectName("StatsPanel")
        self.history: list[dict[str, float | None]] = []
        self._font_scale = 1.0

        self.title = QLabel("实时运营看板")
        self.title.setObjectName("StatsTitle")
        self.subtitle = QLabel("拥堵、队列、座位与通行效率实时概览")
        self.subtitle.setObjectName("StatsSubtitle")

        self.table = QTableWidget(0, 2)
        self.table.setObjectName("StatsTable")
        self.table.setHorizontalHeaderLabels(["指标", "当前值"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(260)

        table_card = _card()
        table_layout = QVBoxLayout()
        table_layout.setContentsMargins(10, 10, 10, 10)
        table_layout.addWidget(self.table)
        table_card.setLayout(table_layout)

        self.gauge_panel = GaugePanel()
        self.table_type_panel = TableTypeUtilizationPanel()
        self.heatmap = QueueHeatmap()
        self.trend = TrendChart()
        self.sections: list[CollapsibleSection] = []

        content = QWidget()
        content.setObjectName("StatsScrollContent")
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(14, 16, 14, 16)
        self.content_layout.setSpacing(14)
        self.content_layout.addWidget(self.title)
        self.content_layout.addWidget(self.subtitle)

        self.core_section = CollapsibleSection("核心仪表盘", expanded=True)
        self.core_section.set_content(self.gauge_panel)
        self.core_section.setToolTip("核心运营指标。拥堵超过 80% 时标题会高亮。")

        operations_content = QWidget()
        operations_layout = QVBoxLayout()
        operations_layout.setContentsMargins(0, 0, 0, 0)
        operations_layout.setSpacing(12)
        operations_layout.addWidget(self.table_type_panel)
        operations_layout.addWidget(self.heatmap)
        operations_content.setLayout(operations_layout)
        self.operations_section = CollapsibleSection("运营分布", expanded=False)
        self.operations_section.set_content(operations_content)
        self.operations_section.setToolTip("包含桌型利用率与窗口队列热力图。点击热力图格子可看详情。")

        detail_content = QWidget()
        detail_layout = QVBoxLayout()
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(12)
        detail_layout.addWidget(table_card)
        detail_layout.addWidget(self.trend)
        detail_content.setLayout(detail_layout)
        self.detail_section = CollapsibleSection("详细指标", expanded=False)
        self.detail_section.set_content(detail_content)
        self.detail_section.setToolTip("展开查看完整指标表和趋势折线图，点击趋势图可放大。")

        self.sections = [self.core_section, self.operations_section, self.detail_section]
        for section in self.sections:
            section.dragMoveRequested.connect(self._move_section_by_drag)
            self.content_layout.addWidget(section)
        self.content_layout.addStretch(1)
        content.setLayout(self.content_layout)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("StatsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(content)

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.scroll)
        self.setLayout(root)

        self._apply_style()
        self.set_frame({})

    def apply_font_scale(self, scale: float) -> None:
        self._font_scale = max(0.8, min(1.6, float(scale)))
        self._apply_style()
        self.update()
        self.gauge_panel.update()
        self.table_type_panel.update()
        self.heatmap.update()
        self.trend.update()

    def _apply_style(self) -> None:
        self.title.setFont(ui_font(13, QFont.Weight.Bold))
        font_family = stylesheet_font_family()
        subtitle_size = max(8, round(9 * self._font_scale))
        table_size = max(8, round(9 * self._font_scale))
        style = """
            QWidget#StatsPanel {
                background: #fff7ed;
                border-left: 1px solid #d6c2a8;
            }
            QScrollArea#StatsScroll {
                background: transparent;
            }
            QWidget#StatsScrollContent {
                background: #fff7ed;
            }
            QLabel#StatsTitle {
                color: #0f172a;
            }
            QLabel#StatsSubtitle {
                color: #64748b;
                font: __SUBTITLE_SIZE__pt "Microsoft YaHei UI";
                padding-bottom: 2px;
            }
            QFrame#StatsCard {
                background: #ffffff;
                border: 1px solid #ead7bf;
                border-radius: 12px;
            }
            QFrame#CollapsibleSection {
                background: #fffaf0;
                border: 1px solid #dccdb8;
                border-radius: 16px;
            }
            QFrame#CollapsibleSection:hover {
                background: #fffdf7;
                border-color: #0f766e;
            }
            QFrame#CollapsibleSection[pressed="true"] {
                background: #fff1d8;
            }
            QFrame#SectionHeader {
                background: transparent;
                border-radius: 16px;
            }
            QFrame#SectionHeader:hover {
                background: rgba(15, 118, 110, 16);
            }
            QFrame#SectionHeader[expanded="true"] {
                background: rgba(15, 118, 110, 12);
            }
            QFrame#SectionHeader[pressed="true"] {
                background: rgba(15, 118, 110, 26);
            }
            QFrame#SectionHeader[alert="true"] {
                background: rgba(217, 80, 111, 24);
            }
            QLabel#SectionTitle {
                color: #17211f;
                font: 900 15pt "Microsoft YaHei UI";
            }
            QFrame#SectionHeader[expanded="true"] QLabel#SectionTitle {
                color: #0f5f59;
            }
            QWidget#SectionBody {
                background: transparent;
            }
            QTableWidget#StatsTable {
                background: transparent;
                alternate-background-color: #f8fafc;
                border: 0;
                color: #0f172a;
                font: __TABLE_SIZE__pt "Microsoft YaHei UI";
            }
            QHeaderView::section {
                background: #eaf1f8;
                border: 0;
                border-radius: 6px;
                color: #334155;
                font-weight: 700;
                padding: 7px 8px;
            }
            QTableWidget::item {
                border-bottom: 1px solid #eef2f7;
                padding: 6px 8px;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 4px 2px 4px 2px;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
                border-radius: 4px;
                min-height: 40px;
            }
            QScrollBar::handle:vertical:hover {
                background: #94a3b8;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
            """
        self.setStyleSheet(
            style.replace("__SUBTITLE_SIZE__", str(subtitle_size))
            .replace("__TABLE_SIZE__", str(table_size))
            .replace("Microsoft YaHei UI", font_family)
        )

    def set_frame(self, frame: dict | None) -> None:
        frame = frame or {}
        stats = frame.get("stats") or {}
        if not isinstance(stats, dict):
            stats = {}

        game_time = _number(frame.get("game_time"), None)
        avg_wait_time = _number(stats.get("avg_wait_time"), None)
        max_active = _number(stats.get("max_active_students"), None)
        congestion_index = _number(stats.get("congestion_index"), None)
        stuck_student_count = _number(stats.get("stuck_student_count"), None)
        avg_queue_length = _number(stats.get("avg_queue_length"), None)
        if game_time is not None:
            self.history.append(
                {
                    "game_time": game_time,
                    "avg_wait_time": avg_wait_time,
                    "max_active_students": max_active,
                    "congestion_index": congestion_index,
                    "stuck_student_count": stuck_student_count,
                    "avg_queue_length": avg_queue_length,
                }
            )
            self.history = self.history[-160:]

        queue_stats = stats.get("stall_queue_stats") or []
        queue_rows = [
            (
                f"W{int(_number(item.get('stall_id'), 0)) + 1} 最大队列",
                _display_value(item.get("max_queue_length")),
            )
            for item in queue_stats
            if isinstance(item, dict)
        ]

        rows = [
            ("平均等待时间", _format_seconds(stats.get("avg_wait_time"))),
            ("平均实际用餐时间", _format_seconds(stats.get("avg_eating_time"))),
            ("平均在场总耗时", _format_seconds(stats.get("avg_total_time"))),
            ("场内最大人数", _display_value(stats.get("max_active_students"))),
            ("座位利用率", _format_percent(stats.get("seat_utilization"))),
            ("平均移动速度", _format_speed(stats.get("avg_move_speed"))),
            ("拥堵指数", _format_percent(stats.get("congestion_index"))),
            ("当前卡住人数", _display_value(stats.get("stuck_student_count"))),
            ("累计重规划", _display_value(stats.get("reroute_count"))),
            ("平均队列长度", _format_decimal(stats.get("avg_queue_length"))),
            ("回收口等待", _display_value(stats.get("tray_return_queue_length"))),
            *queue_rows,
        ]
        if not queue_rows:
            rows.append(("窗口最大队列", "-"))

        self.table.setRowCount(len(rows))
        for row_index, (label, value) in enumerate(rows):
            label_item = QTableWidgetItem(label)
            value_item = QTableWidgetItem(value)
            value_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row_index, 0, label_item)
            self.table.setItem(row_index, 1, value_item)
        self.table.resizeRowsToContents()

        self.gauge_panel.set_stats(stats)
        self.table_type_panel.set_data(_table_type_utilization(frame, stats))
        self.heatmap.set_frame(frame)
        self.trend.set_history(self.history)

        congestion = _number(stats.get("congestion_index"), 0.0) or 0.0
        queue_values = self.heatmap._heatmap_values()
        max_queue = max((value for _, value in queue_values), default=0)
        self.core_section.set_alert(congestion >= 0.8)
        self.operations_section.set_alert(max_queue >= 8)

    def _move_section_by_drag(self, section: "CollapsibleSection", delta_y: int) -> None:
        if abs(delta_y) < 26 or section not in self.sections:
            return
        index = self.sections.index(section)
        target = index + (1 if delta_y > 0 else -1)
        if target < 0 or target >= len(self.sections):
            return
        self.sections[index], self.sections[target] = self.sections[target], self.sections[index]
        for item in self.sections:
            self.content_layout.removeWidget(item)
        insert_index = 2
        for item in self.sections:
            self.content_layout.insertWidget(insert_index, item)
            insert_index += 1


class CollapsibleHeader(QFrame):
    dragMoveRequested = pyqtSignal(object, int)

    def __init__(self, section: "CollapsibleSection", title: str) -> None:
        super().__init__(section)
        self.section = section
        self._press_pos: QPoint | None = None
        self.setObjectName("SectionHeader")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.arrow = ArrowIcon()
        self.title = QLabel(title)
        self.title.setObjectName("SectionTitle")

        layout = QHBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        layout.addWidget(self.arrow)
        layout.addWidget(self.title, 1)
        self.setLayout(layout)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self.section.set_pressed(True)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._press_pos is not None:
            delta = event.position().toPoint() - self._press_pos
            if abs(delta.y()) > 26 and abs(delta.y()) > abs(delta.x()):
                self.dragMoveRequested.emit(self.section, delta.y())
                self._press_pos = event.position().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        moved = False
        if self._press_pos is not None:
            delta = event.position().toPoint() - self._press_pos
            moved = abs(delta.y()) > 8 or abs(delta.x()) > 8
        self._press_pos = None
        self.section.set_pressed(False)
        if event.button() == Qt.MouseButton.LeftButton and not moved:
            self.section.toggle()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ArrowIcon(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self._angle = 0.0
        self.setFixedSize(18, 18)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("color: #0f766e; font: 900 13pt 'Microsoft YaHei UI';")
        self.setText("v")

    def get_angle(self) -> float:
        return self._angle

    def set_angle(self, value: float) -> None:
        self._angle = value
        self.setText(">" if value < -45 else "v")

    angle = pyqtProperty(float, fget=get_angle, fset=set_angle)


class CollapsibleSection(QFrame):
    dragMoveRequested = pyqtSignal(object, int)

    def __init__(self, title: str, *, expanded: bool) -> None:
        super().__init__()
        self.setObjectName("CollapsibleSection")
        self._expanded = expanded
        self._pressed = False
        self._alert = False
        self._arrow_animation: QPropertyAnimation | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header = CollapsibleHeader(self, title)
        self.header.dragMoveRequested.connect(self.dragMoveRequested.emit)
        self.body = QWidget()
        self.body.setObjectName("SectionBody")
        self.body.setVisible(expanded)
        self.body_layout = QVBoxLayout()
        self.body_layout.setContentsMargins(14, 10, 14, 14)
        self.body_layout.setSpacing(12)
        self.body.setLayout(self.body_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.body)
        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._sync_state(animated=False)

    def set_content(self, widget: QWidget) -> None:
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            existing = item.widget()
            if existing is not None:
                existing.setParent(None)
        self.body_layout.addWidget(widget)

    def toggle(self) -> None:
        self._expanded = not self._expanded
        self._sync_state(animated=True)

    def set_alert(self, alert: bool) -> None:
        if self._alert == alert:
            return
        self._alert = alert
        self._sync_state(animated=False)

    def set_pressed(self, pressed: bool) -> None:
        self._pressed = pressed
        self._sync_state(animated=False)

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(hint.width(), max(62, hint.height()))

    def _sync_state(self, *, animated: bool) -> None:
        self.setProperty("pressed", self._pressed)
        self.header.setProperty("pressed", self._pressed)
        self.header.setProperty("alert", self._alert)
        self.header.setProperty("expanded", self._expanded)
        for widget in (self, self.header):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

        target_angle = 0.0 if self._expanded else -90.0
        if not animated:
            self.header.arrow.set_angle(target_angle)
            self.body.setVisible(self._expanded)
            return

        self.body.setVisible(self._expanded)
        if self._arrow_animation is not None:
            self._arrow_animation.stop()
        self._arrow_animation = QPropertyAnimation(self.header.arrow, b"angle", self)
        self._arrow_animation.setDuration(220)
        self._arrow_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._arrow_animation.setStartValue(self.header.arrow.get_angle())
        self._arrow_animation.setEndValue(target_angle)
        self._arrow_animation.start()


class GaugePanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(300)
        self.stats: dict[str, Any] = {}

    def set_stats(self, stats: dict[str, Any]) -> None:
        self.stats = stats
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = _card_painter(self)
        gauges = [
            ("等待", _number(self.stats.get("avg_wait_time"), None), 120.0, "s"),
            ("在场", _number(self.stats.get("avg_total_time"), None), 600.0, "s"),
            ("座位", _number(self.stats.get("seat_utilization"), None), 1.0, "%"),
            ("人数", _number(self.stats.get("max_active_students"), None), 120.0, "人"),
            ("拥堵", _number(self.stats.get("congestion_index"), None), 1.0, "%"),
            ("卡住", _number(self.stats.get("stuck_student_count"), None), 20.0, "人"),
        ]

        cell_width = (self.width() - 44) / 2
        for index, (label, value, maximum, unit) in enumerate(gauges):
            col = index % 2
            row = index // 2
            rect = QRectF(16 + col * (cell_width + 12), 18 + row * 76, cell_width, 66)
            color = self._semantic_color(label, value)
            self._draw_gauge(painter, rect, label, value, maximum, unit, color)

    def _draw_gauge(
        self,
        painter: QPainter,
        rect: QRectF,
        label: str,
        value: float | None,
        maximum: float,
        unit: str,
        color: QColor,
    ) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(StatsTokens.CARD_BG))
        painter.drawRoundedRect(rect, 8, 8)

        center = rect.left() + 36
        circle = QRectF(center - 22, rect.top() + 11, 44, 44)
        track_pen = QPen(QColor(StatsTokens.TRACK), 7)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(circle, 210 * 16, -240 * 16)
        if value is not None:
            ratio = max(0.0, min(1.0, value / maximum if maximum > 0 else 0.0))
            progress_pen = QPen(color, 7)
            progress_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(progress_pen)
            painter.drawArc(circle, 210 * 16, int(-240 * ratio * 16))

        painter.setPen(QColor(StatsTokens.MUTED))
        painter.setFont(ui_font(8))
        painter.drawText(QRectF(rect.left() + 72, rect.top() + 12, rect.width() - 82, 18), Qt.AlignmentFlag.AlignLeft, label)

        painter.setPen(color.darker(125))
        painter.setFont(ui_font(11, QFont.Weight.Bold))
        if value is None:
            display = "-"
        elif unit == "%":
            display = f"{value * 100:.1f}%"
        elif unit == "s":
            display = _format_seconds(value)
        else:
            display = f"{int(value)}{unit}"
        painter.drawText(QRectF(rect.left() + 72, rect.top() + 32, rect.width() - 82, 22), Qt.AlignmentFlag.AlignLeft, display)

    def _semantic_color(self, label: str, value: float | None) -> QColor:
        if value is None:
            return QColor(StatsTokens.MUTED)
        if label == "在场":
            return QColor(StatsTokens.THEME)
        thresholds = StatsTokens.GAUGE_THRESHOLDS.get(label)
        if thresholds is None:
            return QColor(StatsTokens.HEALTHY)
        low_caution = thresholds.get("low_caution")
        if low_caution is not None and value <= low_caution:
            return QColor(StatsTokens.CAUTION)
        if value >= thresholds["alert"]:
            return QColor(StatsTokens.ALERT)
        if value >= thresholds["caution"]:
            return QColor(StatsTokens.CAUTION)
        return QColor(StatsTokens.HEALTHY)


class TableTypeUtilizationPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(176)
        self.rows: list[tuple[str, float | None, int | None, int | None]] = []

    def set_data(self, rows: list[tuple[str, float | None, int | None, int | None]]) -> None:
        self.rows = rows
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = _card_painter(self)
        painter.setPen(QColor("#0f172a"))
        painter.setFont(ui_font(10, QFont.Weight.Bold))
        painter.drawText(QRectF(16, 14, self.width() - 32, 20), Qt.AlignmentFlag.AlignLeft, "桌型利用率")

        rows = self.rows or [("2人桌", None, None, None), ("4人桌", None, None, None), ("6人桌", None, None, None)]
        top = 48.0
        bar_left = 76.0
        bar_width = max(80.0, self.width() - bar_left - 60.0)
        for index, (label, ratio, used, total) in enumerate(rows):
            y = top + index * 36.0
            color = _utilization_color(ratio)
            painter.setPen(QColor("#334155"))
            painter.setFont(ui_font(8, QFont.Weight.Bold))
            painter.drawText(QRectF(16, y - 2, 54, 18), Qt.AlignmentFlag.AlignLeft, label)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(StatsTokens.TRACK))
            painter.drawRoundedRect(QRectF(bar_left, y, bar_width, 12), 6, 6)
            if ratio is not None:
                ratio = max(0.0, min(1.0, ratio))
                painter.setBrush(color)
                painter.drawRoundedRect(QRectF(bar_left, y, bar_width * ratio, 12), 6, 6)

            painter.setPen(QColor("#0f172a"))
            painter.setFont(ui_font(8, QFont.Weight.Bold))
            percent = "-" if ratio is None else f"{ratio * 100:.1f}%"
            painter.drawText(QRectF(bar_left + bar_width + 8, y - 3, 44, 18), Qt.AlignmentFlag.AlignRight, percent)

            painter.setPen(QColor("#64748b"))
            painter.setFont(ui_font(7))
            detail = "-" if used is None or total is None else f"{used}/{total} 座"
            painter.drawText(QRectF(bar_left, y + 14, bar_width, 14), Qt.AlignmentFlag.AlignLeft, detail)


class QueueHeatmap(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(260)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stats: dict[str, Any] = {}
        self.frame: dict[str, Any] = {}
        self._cell_rects: list[tuple[QRectF, int]] = []
        self._popup: QueueDetailPopup | None = None

    def set_stats(self, stats: dict[str, Any]) -> None:
        self.stats = stats
        self.update()

    def set_frame(self, frame: dict[str, Any]) -> None:
        self.frame = frame if isinstance(frame, dict) else {}
        stats = self.frame.get("stats") or {}
        self.stats = stats if isinstance(stats, dict) else {}
        self.update()
        if self._popup is not None:
            self._popup.update_frame(self.frame)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            for rect, stall_id in self._cell_rects:
                if rect.contains(pos):
                    self._open_detail(stall_id)
                    break
        super().mousePressEvent(event)

    def _open_detail(self, stall_id: int) -> None:
        if self._popup is not None:
            self._popup.close()
        self._popup = QueueDetailPopup(stall_id, self.frame, self.window())
        self._popup.finished.connect(self._on_popup_closed)
        self._popup.show()

    def _on_popup_closed(self) -> None:
        self._popup = None

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = _card_painter(self)
        painter.setPen(QColor("#0f172a"))
        painter.setFont(ui_font(10, QFont.Weight.Bold))
        painter.drawText(QRectF(16, 14, self.width() - 32, 20), Qt.AlignmentFlag.AlignLeft, "窗口队列热力图")

        self._cell_rects = []
        values = self._heatmap_values()
        if not values:
            painter.setPen(QColor("#64748b"))
            painter.setFont(ui_font(9))
            painter.drawText(QRectF(16, 48, self.width() - 32, self.height() - 82), Qt.AlignmentFlag.AlignCenter, "暂无队列数据")
            self._draw_legend(painter, 16, self.height() - 32, self.width() - 32)
            return

        max_value = max(1, max(value for _, value in values))
        cols = 4
        gap = 10.0
        area = QRectF(16, 50, self.width() - 32, self.height() - 96)
        cell_width = (area.width() - gap * (cols - 1)) / cols
        rows = (len(values) + cols - 1) // cols
        cell_height = min(52.0, (area.height() - gap * max(0, rows - 1)) / max(1, rows))

        for index, (stall_id, value) in enumerate(values):
            row = index // cols
            col = index % cols
            rect = QRectF(
                area.left() + col * (cell_width + gap),
                area.top() + row * (cell_height + gap),
                cell_width,
                cell_height,
            )
            self._cell_rects.append((QRectF(rect), stall_id))
            color = _heat_color(value / max_value)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 8, 8)
            painter.setPen(QColor("#ffffff" if value / max_value > 0.78 else "#17211f"))
            painter.setFont(ui_font(10, QFont.Weight.Bold))
            painter.drawText(rect.adjusted(8, 6, -8, -24), Qt.AlignmentFlag.AlignLeft, f"W{stall_id + 1}")
            painter.setFont(ui_font(13, QFont.Weight.Bold))
            painter.drawText(rect.adjusted(8, 22, -8, -6), Qt.AlignmentFlag.AlignRight, str(value))

        self._draw_legend(painter, 16, self.height() - 32, self.width() - 32)

    def _heatmap_values(self) -> list[tuple[int, int]]:
        max_by_stall: dict[int, int] = {}
        queue_stats = self.stats.get("stall_queue_stats") or []
        if isinstance(queue_stats, list):
            for item in queue_stats:
                if not isinstance(item, dict):
                    continue
                stall_id = int(_number(item.get("stall_id"), 0) or 0)
                max_by_stall[stall_id] = int(_number(item.get("max_queue_length"), 0) or 0)

        current_by_stall: dict[int, int] = {}
        stalls = self.frame.get("stalls") or []
        if isinstance(stalls, list):
            for stall in stalls:
                if not isinstance(stall, dict):
                    continue
                stall_id = int(_number(stall.get("id"), 0) or 0)
                current_by_stall[stall_id] = int(_number(stall.get("queue_count"), 0) or 0)

        stall_ids = sorted(set(max_by_stall) | set(current_by_stall))
        return [
            (stall_id, max(max_by_stall.get(stall_id, 0), current_by_stall.get(stall_id, 0)))
            for stall_id in stall_ids
        ]

    def _draw_legend(self, painter: QPainter, left: float, top: float, width: float) -> None:
        painter.setFont(ui_font(8))
        painter.setPen(QColor("#64748b"))
        painter.drawText(QRectF(left, top - 18, width, 16), Qt.AlignmentFlag.AlignLeft, "低拥堵")
        painter.drawText(QRectF(left, top - 18, width, 16), Qt.AlignmentFlag.AlignRight, "高拥堵")
        steps = 24
        segment = width / steps
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(steps):
            painter.setBrush(_heat_color(index / max(1, steps - 1)))
            painter.drawRect(QRectF(left + index * segment, top, segment + 1, 8))


class QueueDetailPopup(QDialog):
    def __init__(self, stall_id: int, frame: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stall_id = stall_id
        self._frame = frame if isinstance(frame, dict) else {}
        self._metric_labels: dict[str, QLabel] = {}
        self._orders_scroll: QScrollArea | None = None

        self.setWindowTitle(f"窗口 {stall_id + 1} 队列详情")
        self.setMinimumSize(420, 520)
        self.resize(460, 600)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        root = QVBoxLayout()
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel(f"窗口 {stall_id + 1} 队列详情")
        title.setFont(ui_font(14, QFont.Weight.Bold))
        title.setStyleSheet("color: #0f172a;")
        root.addWidget(title)

        metrics = QHBoxLayout()
        metrics.setSpacing(8)
        for key, label in (
            ("queue", "当前队列"),
            ("max", "历史最大"),
            ("queued", "排队"),
            ("cooking", "出餐中"),
        ):
            metrics.addWidget(self._metric_card(key, label))
        root.addLayout(metrics)

        subtitle = QLabel("学生订单")
        subtitle.setFont(ui_font(10, QFont.Weight.Bold))
        subtitle.setStyleSheet("color: #334155; padding-top: 2px;")
        root.addWidget(subtitle)

        self._orders_scroll = QScrollArea()
        self._orders_scroll.setWidgetResizable(True)
        self._orders_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._orders_scroll.setStyleSheet("QScrollArea { background: transparent; }")
        root.addWidget(self._orders_scroll, 1)

        self.setLayout(root)
        self._apply_style()
        self._refresh()

    def stall_id(self) -> int:
        return self._stall_id

    def update_frame(self, frame: dict[str, Any]) -> None:
        self._frame = frame if isinstance(frame, dict) else {}
        self._refresh()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #ffffff;
            }
            QFrame#QueueMetricCard {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
            QFrame#QueueOrderCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
            QProgressBar {
                background: #e2e8f0;
                border: 0;
                border-radius: 5px;
                height: 10px;
            }
            QProgressBar::chunk {
                background: #0ea5e9;
                border-radius: 5px;
            }
            """
        )

    def _metric_card(self, key: str, label: str) -> QFrame:
        card = QFrame()
        card.setObjectName("QueueMetricCard")
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(3)

        name = QLabel(label)
        name.setFont(ui_font(8))
        name.setStyleSheet("color: #64748b;")
        value = QLabel("-")
        value.setFont(ui_font(13, QFont.Weight.Bold))
        value.setStyleSheet("color: #0f172a;")
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._metric_labels[key] = value

        layout.addWidget(name)
        layout.addWidget(value)
        card.setLayout(layout)
        return card

    def _refresh(self) -> None:
        stall = _stall_by_id(self._frame, self._stall_id) or {}
        orders = _active_orders_for_stall(self._frame, self._stall_id)
        queued_count = sum(1 for order in orders if _effective_order_status(order, self._frame) == "queued")
        cooking_count = sum(1 for order in orders if _effective_order_status(order, self._frame) == "cooking")
        current_queue = int(_number(stall.get("queue_count"), len(orders)) or 0)
        max_queue = _queue_stat_max(self._frame, self._stall_id)

        self._set_metric("queue", current_queue)
        self._set_metric("max", max_queue if max_queue is not None else "-")
        self._set_metric("queued", queued_count)
        self._set_metric("cooking", cooking_count)

        if self._orders_scroll is not None:
            self._orders_scroll.setWidget(self._orders_content(stall, orders))

    def _set_metric(self, key: str, value: object) -> None:
        label = self._metric_labels.get(key)
        if label is not None:
            label.setText(str(value))

    def _orders_content(self, stall: dict[str, Any], orders: list[dict[str, Any]]) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        if not orders:
            empty = QLabel("当前没有等待取餐的学生")
            empty.setFont(ui_font(10))
            empty.setStyleSheet("color: #94a3b8; padding: 30px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty)
            layout.addStretch()
            container.setLayout(layout)
            return container

        dish_names = _dish_names(stall)
        students = _students_by_id(self._frame)
        for order in orders:
            layout.addWidget(self._order_card(order, dish_names, students))
        layout.addStretch()
        container.setLayout(layout)
        return container

    def _order_card(
        self,
        order: dict[str, Any],
        dish_names: dict[int, str],
        students: dict[int, dict[str, Any]],
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("QueueOrderCard")
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        student_id = int(_number(order.get("student_id"), 0) or 0)
        dish_id = int(_number(order.get("dish_id"), 0) or 0)
        dish_name = dish_names.get(dish_id, f"菜品 {dish_id}" if dish_id else "-")
        status = _effective_order_status(order, self._frame)
        remaining = _order_remaining(order, self._frame)
        progress = _order_progress(order, self._frame)
        student = students.get(student_id, {})
        state = _student_state_label(str(student.get("state") or ""))

        top = QHBoxLayout()
        top.setSpacing(8)
        student_label = QLabel(f"S{student_id}")
        student_label.setFont(ui_font(11, QFont.Weight.Bold))
        student_label.setStyleSheet("color: #0f172a;")
        top.addWidget(student_label)
        dish_label = QLabel(dish_name)
        dish_label.setFont(ui_font(10, QFont.Weight.Bold))
        dish_label.setStyleSheet("color: #334155;")
        top.addWidget(dish_label, 1)
        status_label = QLabel(_order_status_label(status))
        status_label.setFont(ui_font(9, QFont.Weight.Bold))
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_label.setStyleSheet(_order_status_style(status))
        top.addWidget(status_label)
        layout.addLayout(top)

        progress_bar = QProgressBar()
        progress_bar.setRange(0, 1000)
        progress_bar.setValue(int(progress * 1000))
        progress_bar.setTextVisible(False)
        layout.addWidget(progress_bar)

        detail = QHBoxLayout()
        detail.setSpacing(8)
        if status == "done":
            wait_text = "已可取餐"
        elif remaining is None:
            wait_text = "等待出餐排程"
        else:
            wait_text = f"还需 {_format_seconds(remaining)}"
        left = QLabel(wait_text)
        left.setFont(ui_font(9))
        left.setStyleSheet("color: #475569;")
        detail.addWidget(left)
        detail.addStretch()
        right = QLabel(state or f"订单 #{_display_value(order.get('id'))}")
        right.setFont(ui_font(9))
        right.setStyleSheet("color: #64748b;")
        detail.addWidget(right)
        layout.addLayout(detail)

        card.setLayout(layout)
        return card


def _draw_trend_lines(
    painter: QPainter,
    chart: QRectF,
    history: list[dict[str, float | None]],
) -> None:
    """共享的折线图核心绘图逻辑，供内嵌图表和弹窗复用。"""
    if len(history) < 2:
        painter.setPen(QColor("#64748b"))
        painter.setFont(ui_font(9))
        painter.drawText(chart, Qt.AlignmentFlag.AlignCenter, "运行后显示趋势")
        return

    wait_values = [item["avg_wait_time"] for item in history if item.get("avg_wait_time") is not None]
    active_values = [item["max_active_students"] for item in history if item.get("max_active_students") is not None]
    congestion_values = [item["congestion_index"] for item in history if item.get("congestion_index") is not None]
    stuck_values = [item["stuck_student_count"] for item in history if item.get("stuck_student_count") is not None]
    max_wait = max(1.0, max(wait_values) if wait_values else 1.0)
    max_active = max(1.0, max(active_values) if active_values else 1.0)
    max_congestion = max(0.15, max(congestion_values) if congestion_values else 0.15)
    max_stuck = max(1.0, max(stuck_values) if stuck_values else 1.0)

    _draw_single_line(painter, chart, history, "avg_wait_time", max_wait, QColor("#0ea5e9"), y_offset=-3)
    _draw_single_line(painter, chart, history, "max_active_students", max_active, QColor(StatsTokens.CAUTION), y_offset=1)
    _draw_single_line(painter, chart, history, "congestion_index", max_congestion, QColor(StatsTokens.ALERT), y_offset=4)
    _draw_single_line(painter, chart, history, "stuck_student_count", max_stuck, QColor(StatsTokens.CAUTION), y_offset=7)


def _draw_single_line(
    painter: QPainter,
    chart: QRectF,
    history: list[dict[str, float | None]],
    key: str,
    maximum: float,
    color: QColor,
    y_offset: float = 0.0,
) -> None:
    points: list[tuple[float, float]] = []
    total = max(1, len(history) - 1)
    for index, item in enumerate(history):
        value = item.get(key)
        if value is None:
            continue
        x = chart.left() + chart.width() * index / total
        y = chart.bottom() - chart.height() * max(0.0, min(1.0, float(value) / maximum)) + y_offset
        y = max(chart.top(), min(chart.bottom(), y))
        points.append((x, y))
    if len(points) < 2:
        return

    painter.setPen(QPen(color, 2.5))
    for start, end in zip(points, points[1:]):
        painter.drawLine(int(start[0]), int(start[1]), int(end[0]), int(end[1]))

    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    for x, y in points[-4:]:
        painter.drawEllipse(QRectF(x - 3, y - 3, 6, 6))


def _draw_y_axis(painter: QPainter, chart: QRectF) -> None:
    """在图表左侧绘制归一化纵轴刻度标签 (0% ~ 100%)。"""
    painter.setPen(QColor("#94a3b8"))
    painter.setFont(ui_font(7))
    labels = ["100%", "67%", "33%", "0%"]
    for i in range(4):
        y = chart.top() + i * chart.height() / 3
        label = labels[i]
        # 刻度短线
        painter.drawLine(int(chart.left() - 5), int(y), int(chart.left()), int(y))
        # 标签
        label_rect = QRectF(chart.left() - 34, y - 8, 30, 16)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)


def _draw_trend_legend(painter: QPainter, width: int, height: int) -> None:
    y = height - 28
    items = [
        ("等待", QColor("#0ea5e9")),
        ("人数", QColor(StatsTokens.CAUTION)),
        ("拥堵", QColor(StatsTokens.ALERT)),
        ("卡住", QColor(StatsTokens.CAUTION)),
    ]
    item_count = len(items)
    block_width = 72
    total_width = item_count * block_width
    start_x = (width - total_width) // 2
    x = start_x if start_x > 16 else 18
    painter.setFont(ui_font(8))
    for label, color in items:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(x, y + 4, 18, 6), 3, 3)
        painter.setPen(QColor("#475569"))
        painter.drawText(QRectF(x + 24, y - 2, 44, 18), Qt.AlignmentFlag.AlignLeft, label)
        x += block_width


class TrendChart(QWidget):
    """内嵌的趋势折线图，点击可弹出实时同步的放大窗口。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(280)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history: list[dict[str, float | None]] = []
        self._popup: TrendChartPopup | None = None

    def set_history(self, history: list[dict[str, float | None]]) -> None:
        self.history = list(history)
        self.update()
        if self._popup is not None:
            self._popup._chart.history = self.history
            self._popup._chart.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and len(self.history) >= 2:
            if self._popup is not None:
                self._popup.close()
            self._popup = TrendChartPopup(self.history, self.window())
            self._popup.finished.connect(self._on_popup_closed)
            self._popup.show()
        super().mousePressEvent(event)

    def _on_popup_closed(self) -> None:
        self._popup = None

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = _card_painter(self)
        painter.setPen(QColor("#0f172a"))
        painter.setFont(ui_font(10, QFont.Weight.Bold))
        painter.drawText(QRectF(16, 14, self.width() - 32, 20), Qt.AlignmentFlag.AlignLeft, "等待、人数与拥堵趋势")

        chart = QRectF(34, 54, self.width() - 58, self.height() - 92)
        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        for index in range(4):
            y = chart.top() + index * chart.height() / 3
            painter.drawLine(int(chart.left()), int(y), int(chart.right()), int(y))

        _draw_y_axis(painter, chart)
        _draw_trend_lines(painter, chart, self.history)
        _draw_trend_legend(painter, self.width(), self.height())


class TrendChartPopup(QDialog):
    """点击折线图后弹出的实时同步放大趋势图窗口。"""

    def __init__(self, history: list[dict[str, float | None]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("趋势图 — 等待、人数与拥堵放大")
        self.setMinimumSize(720, 440)
        self.resize(880, 500)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._chart = _PopupChart(history)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._chart)
        self.setLayout(layout)


class _PopupChart(QWidget):
    """弹窗内部的大尺寸趋势图绘制组件，持有共享 history 引用实现实时更新。"""

    def __init__(self, history: list[dict[str, float | None]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.history = history

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())

        title_rect = QRectF(24, 20, self.width() - 48, 28)
        painter.setPen(QColor("#0f172a"))
        painter.setFont(ui_font(14, QFont.Weight.Bold))
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft, "等待、人数与拥堵趋势")

        chart = QRectF(48, 68, self.width() - 80, self.height() - 120)
        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        for index in range(4):
            y = chart.top() + index * chart.height() / 3
            painter.drawLine(int(chart.left()), int(y), int(chart.right()), int(y))

        _draw_y_axis(painter, chart)
        _draw_trend_lines(painter, chart, self.history)
        _draw_trend_legend(painter, self.width(), self.height())


def _card() -> QFrame:
    frame = QFrame()
    frame.setObjectName("StatsCard")
    return frame


def _card_painter(widget: QWidget) -> QPainter:
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    bounds = QRectF(0, 0, widget.width() - 1, widget.height() - 1)
    painter.setPen(QPen(QColor("#e2e8f0"), 1))
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(bounds.adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
    return painter


def _utilization_color(ratio: float | None) -> QColor:
    if ratio is None:
        return QColor(StatsTokens.MUTED)
    ratio = max(0.0, min(1.0, ratio))
    thresholds = StatsTokens.TABLE_UTILIZATION_THRESHOLDS
    if ratio >= thresholds["alert"]:
        return QColor(StatsTokens.ALERT)
    if ratio >= thresholds["caution"]:
        return QColor(StatsTokens.CAUTION)
    return QColor(StatsTokens.HEALTHY)


def _heat_color(ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, ratio))
    stops = [(position, QColor(color)) for position, color in StatsTokens.HEAT_STOPS]
    for index in range(len(stops) - 1):
        start_pos, start_color = stops[index]
        end_pos, end_color = stops[index + 1]
        if ratio <= end_pos:
            span = max(0.001, end_pos - start_pos)
            return _mix_color(start_color, end_color, (ratio - start_pos) / span)
    return stops[-1][1]


def _mix_color(start: QColor, end: QColor, ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, ratio))
    return QColor(
        int(start.red() + (end.red() - start.red()) * ratio),
        int(start.green() + (end.green() - start.green()) * ratio),
        int(start.blue() + (end.blue() - start.blue()) * ratio),
    )


def _stall_by_id(frame: dict[str, Any], stall_id: int) -> dict[str, Any] | None:
    stalls = frame.get("stalls") or []
    if not isinstance(stalls, list):
        return None
    for stall in stalls:
        if isinstance(stall, dict) and int(_number(stall.get("id"), -1) or -1) == stall_id:
            return stall
    return None


def _queue_stat_max(frame: dict[str, Any], stall_id: int) -> int | None:
    stats = frame.get("stats") or {}
    if not isinstance(stats, dict):
        return None
    queue_stats = stats.get("stall_queue_stats") or []
    if not isinstance(queue_stats, list):
        return None
    for item in queue_stats:
        if not isinstance(item, dict):
            continue
        if int(_number(item.get("stall_id"), -1) or -1) == stall_id:
            return int(_number(item.get("max_queue_length"), 0) or 0)
    return None


def _active_orders_for_stall(frame: dict[str, Any], stall_id: int) -> list[dict[str, Any]]:
    stall = _stall_by_id(frame, stall_id) or {}
    raw_orders = stall.get("orders") or []
    orders: list[dict[str, Any]] = []
    seen_students: set[int] = set()
    if isinstance(raw_orders, list):
        for order in raw_orders:
            if not isinstance(order, dict):
                continue
            normalized = dict(order)
            status = _effective_order_status(normalized, frame)
            if status not in {"queued", "cooking"}:
                continue
            normalized["status"] = status
            student_id = int(_number(order.get("student_id"), 0) or 0)
            if student_id:
                seen_students.add(student_id)
            orders.append(normalized)

    students = frame.get("students") or []
    if isinstance(students, list):
        for student in students:
            if not isinstance(student, dict):
                continue
            student_stall_id = _number(student.get("stall_id"), None)
            if student_stall_id is None or int(student_stall_id) != stall_id:
                continue
            state = str(student.get("state") or "")
            if state not in {"moving_to_queue", "queued"}:
                continue
            student_id = int(_number(student.get("id"), 0) or 0)
            if not student_id or student_id in seen_students:
                continue
            orders.append(
                {
                    "id": student.get("order_id"),
                    "student_id": student_id,
                    "stall_id": stall_id,
                    "dish_id": student.get("dish_id"),
                    "status": "queued",
                    "remaining": None,
                    "progress": 0.0,
                }
            )

    return sorted(
        orders,
        key=lambda order: (
            _order_sort_rank(_effective_order_status(order, frame)),
            _number(order.get("estimated_finished_at"), float("inf")) or float("inf"),
            _number(order.get("student_id"), 0) or 0,
        ),
    )


def _effective_order_status(order: dict[str, Any], frame: dict[str, Any]) -> str:
    status = str(order.get("status") or "").lower()
    if status.startswith("orderstatus."):
        status = status.split(".", 1)[1]
    if status == "done" or status == "cancelled":
        return status

    game_time = _number(frame.get("game_time"), None)
    started_at = _number(order.get("started_at"), None)
    estimated_finished_at = _number(order.get("estimated_finished_at", order.get("finished_at")), None)
    progress = _number(order.get("progress"), None)
    if started_at is not None and game_time is not None:
        if estimated_finished_at is None or game_time < estimated_finished_at:
            if game_time >= started_at:
                return "cooking"
    if progress is not None and progress > 0.0 and (estimated_finished_at is None or status != "done"):
        return "cooking"
    if status in {"queued", "cooking"}:
        return status
    return "queued"


def _order_remaining(order: dict[str, Any], frame: dict[str, Any]) -> float | None:
    remaining = _number(order.get("remaining"), None)
    if remaining is not None:
        return max(0.0, remaining)
    game_time = _number(frame.get("game_time"), None)
    estimated_finished_at = _number(order.get("estimated_finished_at", order.get("finished_at")), None)
    if game_time is None or estimated_finished_at is None:
        return None
    return max(0.0, estimated_finished_at - game_time)


def _order_progress(order: dict[str, Any], frame: dict[str, Any]) -> float:
    progress = _number(order.get("progress"), None)
    if progress is not None and progress > 0.0:
        return max(0.0, min(1.0, progress))
    started_at = _number(order.get("started_at"), None)
    estimated_finished_at = _number(order.get("estimated_finished_at", order.get("finished_at")), None)
    game_time = _number(frame.get("game_time"), None)
    if started_at is None or estimated_finished_at is None or game_time is None:
        return 0.0
    total = max(0.001, estimated_finished_at - started_at)
    return max(0.0, min(1.0, (game_time - started_at) / total))


def _order_sort_rank(status: str) -> int:
    return {"cooking": 0, "queued": 1, "done": 2, "cancelled": 3}.get(status, 4)


def _dish_names(stall: dict[str, Any]) -> dict[int, str]:
    dishes = stall.get("dishes") or []
    names: dict[int, str] = {}
    if not isinstance(dishes, list):
        return names
    for dish in dishes:
        if not isinstance(dish, dict):
            continue
        dish_id = _number(dish.get("id"), None)
        if dish_id is None:
            continue
        names[int(dish_id)] = str(dish.get("name") or f"菜品 {int(dish_id)}")
    return names


def _students_by_id(frame: dict[str, Any]) -> dict[int, dict[str, Any]]:
    students = frame.get("students") or []
    result: dict[int, dict[str, Any]] = {}
    if not isinstance(students, list):
        return result
    for student in students:
        if not isinstance(student, dict):
            continue
        student_id = _number(student.get("id"), None)
        if student_id is not None:
            result[int(student_id)] = student
    return result


def _order_status_label(status: str) -> str:
    return {
        "queued": "排队",
        "cooking": "制作",
        "done": "完成",
        "cancelled": "取消",
    }.get(status, status or "-")


def _order_status_style(status: str) -> str:
    fg, bg = {
        "queued": ("#1d4ed8", "#dbeafe"),
        "cooking": ("#c2410c", "#ffedd5"),
        "done": ("#15803d", "#dcfce7"),
        "cancelled": ("#475569", "#f1f5f9"),
    }.get(status, ("#475569", "#f1f5f9"))
    return f"color: {fg}; background: {bg}; border-radius: 6px; padding: 3px 8px;"


def _student_state_label(state: str) -> str:
    return {
        "deciding": "选择中",
        "moving_to_queue": "前往窗口",
        "queued": "队列中",
        "searching_seat": "找座位",
        "waiting_seat": "等座位",
        "moving_to_seat": "前往座位",
        "eating": "用餐中",
        "moving_to_tray_return": "去回收口",
        "leaving": "离场中",
    }.get(state, "")


def _table_type_utilization(
    frame: dict,
    stats: dict[str, Any],
) -> list[tuple[str, float | None, int | None, int | None]]:
    labels = [("two", "2人桌"), ("four", "4人桌"), ("six", "6人桌")]
    raw = stats.get("table_type_utilization")
    if isinstance(raw, dict):
        rows: list[tuple[str, float | None, int | None, int | None]] = []
        for key, label in labels:
            value = raw.get(key)
            ratio, used, total = _parse_table_type_utilization_value(value)
            rows.append((label, ratio, used, total))
        if any(ratio is not None for _, ratio, _, _ in rows):
            return rows
    return _table_type_utilization_from_tables(frame.get("tables") or [])


def _parse_table_type_utilization_value(value: Any) -> tuple[float | None, int | None, int | None]:
    if isinstance(value, dict):
        ratio = _number(
            value.get("utilization", value.get("ratio", value.get("value"))),
            None,
        )
        used = _int_or_none(value.get("used", value.get("occupied", value.get("occupied_seats"))))
        total = _int_or_none(value.get("total", value.get("seat_count", value.get("total_seats"))))
        if ratio is None and used is not None and total:
            ratio = used / total
        return ratio, used, total
    return _number(value, None), None, None


def _table_type_utilization_from_tables(tables: Any) -> list[tuple[str, float | None, int | None, int | None]]:
    buckets = {
        "two": {"used": 0, "total": 0},
        "four": {"used": 0, "total": 0},
        "six": {"used": 0, "total": 0},
    }
    if isinstance(tables, list):
        for table in tables:
            if not isinstance(table, dict):
                continue
            table_type, seat_count = _table_type_and_seat_count(table)
            seats = table.get("seat_frames") or table.get("seats") or []
            used = sum(1 for seat in seats[:seat_count] if _seat_is_used(seat))
            buckets[table_type]["used"] += used
            buckets[table_type]["total"] += seat_count

    labels = [("two", "2人桌"), ("four", "4人桌"), ("six", "6人桌")]
    rows: list[tuple[str, float | None, int | None, int | None]] = []
    for key, label in labels:
        used = buckets[key]["used"]
        total = buckets[key]["total"]
        ratio = used / total if total else None
        rows.append((label, ratio, used if total else None, total if total else None))
    return rows


def _table_type_and_seat_count(table: dict) -> tuple[str, int]:
    table_type = str(table.get("table_type") or "").lower()
    type_to_count = {"two": 2, "four": 4, "six": 6}
    seat_count = int(_number(table.get("seat_count"), type_to_count.get(table_type, 4)))
    if seat_count not in (2, 4, 6):
        seat_count = type_to_count.get(table_type, 4)
    if table_type not in type_to_count:
        table_type = {2: "two", 4: "four", 6: "six"}.get(seat_count, "four")
    return table_type, seat_count


def _seat_is_used(seat: Any) -> bool:
    if isinstance(seat, dict):
        status = str(seat.get("status") or "")
        if status in {"reserved", "occupied"}:
            return True
        if status == "free":
            return False
        return seat.get("student_id") is not None
    return seat is not None


def _int_or_none(value: Any) -> int | None:
    number = _number(value, None)
    if number is None:
        return None
    return int(number)


def _format_seconds(value: Any) -> str:
    if value is None:
        return "-"
    seconds = _number(value, None)
    if seconds is None:
        return "-"
    minutes = int(seconds // 60)
    remaining = int(round(seconds % 60))
    if minutes <= 0:
        return f"{remaining}s"
    return f"{minutes}m {remaining:02d}s"


def _format_percent(value: Any) -> str:
    if value is None:
        return "-"
    number = _number(value, None)
    if number is None:
        return "-"
    return f"{number * 100:.1f}%"


def _format_speed(value: Any) -> str:
    if value is None:
        return "-"
    number = _number(value, None)
    if number is None:
        return "-"
    return f"{number:.1f} px/s"


def _format_decimal(value: Any) -> str:
    if value is None:
        return "-"
    number = _number(value, None)
    if number is None:
        return "-"
    return f"{number:.1f}"


def _display_value(value: Any) -> str:
    if value is None:
        return "-"
    return str(value)


def _number(value: Any, default: float | None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
