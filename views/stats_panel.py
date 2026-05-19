from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from utils.fonts import stylesheet_font_family, ui_font


class StatsPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(330)
        self.setMaximumWidth(410)
        self.setObjectName("StatsPanel")
        self.history: list[dict[str, float | None]] = []

        self.title = QLabel("实时运营看板")
        self.title.setObjectName("StatsTitle")
        self.title.setFont(ui_font(13, QFont.Weight.Bold))
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
        self.heatmap = QueueHeatmap()
        self.trend = TrendChart()

        content = QWidget()
        content.setObjectName("StatsScrollContent")
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(14, 16, 14, 16)
        content_layout.setSpacing(12)
        content_layout.addWidget(self.title)
        content_layout.addWidget(self.subtitle)
        content_layout.addWidget(self.gauge_panel)
        content_layout.addWidget(table_card)
        content_layout.addWidget(self.heatmap)
        content_layout.addWidget(self.trend)
        content_layout.addStretch(1)
        content.setLayout(content_layout)

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

        font_family = stylesheet_font_family()
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
                font: 9pt "Microsoft YaHei UI";
                padding-bottom: 2px;
            }
            QFrame#StatsCard {
                background: #ffffff;
                border: 1px solid #ead7bf;
                border-radius: 12px;
            }
            QTableWidget#StatsTable {
                background: transparent;
                alternate-background-color: #f8fafc;
                border: 0;
                color: #0f172a;
                font: 9pt "Microsoft YaHei UI";
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
        self.setStyleSheet(style.replace("Microsoft YaHei UI", font_family))
        self.set_frame({})

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
            ("平均就餐总耗时", _format_seconds(stats.get("avg_total_time"))),
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
        self.heatmap.set_stats(stats)
        self.trend.set_history(self.history)


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
        painter.setPen(QColor("#0f172a"))
        painter.setFont(ui_font(10, QFont.Weight.Bold))
        painter.drawText(QRectF(16, 14, self.width() - 32, 20), Qt.AlignmentFlag.AlignLeft, "核心仪表盘")

        gauges = [
            ("等待", _number(self.stats.get("avg_wait_time"), None), 120.0, "s", QColor("#0ea5e9")),
            ("总耗时", _number(self.stats.get("avg_total_time"), None), 600.0, "s", QColor("#8b5cf6")),
            ("座位", _number(self.stats.get("seat_utilization"), None), 1.0, "%", QColor("#14b8a6")),
            ("人数", _number(self.stats.get("max_active_students"), None), 120.0, "人", QColor("#f59e0b")),
            ("拥堵", _number(self.stats.get("congestion_index"), None), 1.0, "%", QColor("#ef4444")),
            ("卡住", _number(self.stats.get("stuck_student_count"), None), 20.0, "人", QColor("#f97316")),
        ]

        cell_width = (self.width() - 44) / 2
        for index, (label, value, maximum, unit, color) in enumerate(gauges):
            col = index % 2
            row = index // 2
            rect = QRectF(16 + col * (cell_width + 12), 46 + row * 78, cell_width, 66)
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
        painter.setBrush(QColor("#f8fafc"))
        painter.drawRoundedRect(rect, 8, 8)

        center = rect.left() + 36
        circle = QRectF(center - 22, rect.top() + 11, 44, 44)
        painter.setPen(QPen(QColor("#e2e8f0"), 7))
        painter.drawArc(circle, 210 * 16, -240 * 16)
        if value is not None:
            ratio = max(0.0, min(1.0, value / maximum if maximum > 0 else 0.0))
            painter.setPen(QPen(color, 7))
            painter.drawArc(circle, 210 * 16, int(-240 * ratio * 16))

        painter.setPen(QColor("#64748b"))
        painter.setFont(ui_font(8))
        painter.drawText(QRectF(rect.left() + 72, rect.top() + 12, rect.width() - 82, 18), Qt.AlignmentFlag.AlignLeft, label)

        painter.setPen(QColor("#0f172a"))
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


class QueueHeatmap(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(260)
        self.stats: dict[str, Any] = {}

    def set_stats(self, stats: dict[str, Any]) -> None:
        self.stats = stats
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = _card_painter(self)
        painter.setPen(QColor("#0f172a"))
        painter.setFont(ui_font(10, QFont.Weight.Bold))
        painter.drawText(QRectF(16, 14, self.width() - 32, 20), Qt.AlignmentFlag.AlignLeft, "窗口队列热力图")

        queue_stats = self.stats.get("stall_queue_stats") or []
        values = [
            (
                int(_number(item.get("stall_id"), 0)),
                int(_number(item.get("max_queue_length"), 0)),
            )
            for item in queue_stats
            if isinstance(item, dict)
        ]
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
            color = _heat_color(value / max_value)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 8, 8)
            painter.setPen(QColor("#ffffff" if value / max_value > 0.55 else "#0f172a"))
            painter.setFont(ui_font(10, QFont.Weight.Bold))
            painter.drawText(rect.adjusted(8, 6, -8, -24), Qt.AlignmentFlag.AlignLeft, f"W{stall_id + 1}")
            painter.setFont(ui_font(13, QFont.Weight.Bold))
            painter.drawText(rect.adjusted(8, 22, -8, -6), Qt.AlignmentFlag.AlignRight, str(value))

        self._draw_legend(painter, 16, self.height() - 32, self.width() - 32)

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


class TrendChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(280)
        self.history: list[dict[str, float | None]] = []

    def set_history(self, history: list[dict[str, float | None]]) -> None:
        self.history = list(history)
        self.update()

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

        if len(self.history) < 2:
            painter.setPen(QColor("#64748b"))
            painter.setFont(ui_font(9))
            painter.drawText(chart, Qt.AlignmentFlag.AlignCenter, "运行后显示趋势")
            self._draw_legend(painter)
            return

        wait_values = [item["avg_wait_time"] for item in self.history if item.get("avg_wait_time") is not None]
        active_values = [item["max_active_students"] for item in self.history if item.get("max_active_students") is not None]
        congestion_values = [item["congestion_index"] for item in self.history if item.get("congestion_index") is not None]
        stuck_values = [item["stuck_student_count"] for item in self.history if item.get("stuck_student_count") is not None]
        max_wait = max(1.0, max(wait_values) if wait_values else 1.0)
        max_active = max(1.0, max(active_values) if active_values else 1.0)
        max_congestion = max(0.15, max(congestion_values) if congestion_values else 0.15)
        max_stuck = max(1.0, max(stuck_values) if stuck_values else 1.0)

        self._draw_line(painter, chart, "avg_wait_time", max_wait, QColor("#0ea5e9"))
        self._draw_line(painter, chart, "max_active_students", max_active, QColor("#f59e0b"))
        self._draw_line(painter, chart, "congestion_index", max_congestion, QColor("#ef4444"))
        self._draw_line(painter, chart, "stuck_student_count", max_stuck, QColor("#f97316"))
        self._draw_legend(painter)

    def _draw_line(
        self,
        painter: QPainter,
        chart: QRectF,
        key: str,
        maximum: float,
        color: QColor,
    ) -> None:
        points: list[tuple[float, float]] = []
        total = max(1, len(self.history) - 1)
        for index, item in enumerate(self.history):
            value = item.get(key)
            if value is None:
                continue
            x = chart.left() + chart.width() * index / total
            y = chart.bottom() - chart.height() * max(0.0, min(1.0, float(value) / maximum))
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

    def _draw_legend(self, painter: QPainter) -> None:
        y = self.height() - 28
        items = [
            ("等待", QColor("#0ea5e9")),
            ("人数", QColor("#f59e0b")),
            ("拥堵", QColor("#ef4444")),
            ("卡住", QColor("#f97316")),
        ]
        x = 18
        painter.setFont(ui_font(8))
        for label, color in items:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x, y + 4, 18, 6), 3, 3)
            painter.setPen(QColor("#475569"))
            painter.drawText(QRectF(x + 24, y - 2, 44, 18), Qt.AlignmentFlag.AlignLeft, label)
            x += 72


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


def _heat_color(ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, ratio))
    if ratio < 0.5:
        t = ratio / 0.5
        return QColor(
            int(20 + (14 - 20) * t),
            int(184 + (165 - 184) * t),
            int(166 + (233 - 166) * t),
        )
    t = (ratio - 0.5) / 0.5
    return QColor(
        int(14 + (239 - 14) * t),
        int(165 + (68 - 165) * t),
        int(233 + (68 - 233) * t),
    )


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
