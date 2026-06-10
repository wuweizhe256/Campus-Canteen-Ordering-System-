from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
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

        content = QWidget()
        content.setObjectName("StatsScrollContent")
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(14, 16, 14, 16)
        content_layout.setSpacing(12)
        content_layout.addWidget(self.title)
        content_layout.addWidget(self.subtitle)
        content_layout.addWidget(self.gauge_panel)
        content_layout.addWidget(self.table_type_panel)
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
        self.table_type_panel.set_data(_table_type_utilization(frame, stats))
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
        colors = {
            "2人桌": QColor("#0ea5e9"),
            "4人桌": QColor("#14b8a6"),
            "6人桌": QColor("#f59e0b"),
        }
        for index, (label, ratio, used, total) in enumerate(rows):
            y = top + index * 36.0
            color = colors.get(label, QColor("#64748b"))
            painter.setPen(QColor("#334155"))
            painter.setFont(ui_font(8, QFont.Weight.Bold))
            painter.drawText(QRectF(16, y - 2, 54, 18), Qt.AlignmentFlag.AlignLeft, label)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#f1f5f9"))
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

    _draw_single_line(painter, chart, history, "avg_wait_time", max_wait, QColor("#0ea5e9"))
    _draw_single_line(painter, chart, history, "max_active_students", max_active, QColor("#f59e0b"))
    _draw_single_line(painter, chart, history, "congestion_index", max_congestion, QColor("#ef4444"))
    _draw_single_line(painter, chart, history, "stuck_student_count", max_stuck, QColor("#f97316"))


def _draw_single_line(
    painter: QPainter,
    chart: QRectF,
    history: list[dict[str, float | None]],
    key: str,
    maximum: float,
    color: QColor,
) -> None:
    points: list[tuple[float, float]] = []
    total = max(1, len(history) - 1)
    for index, item in enumerate(history):
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
        ("人数", QColor("#f59e0b")),
        ("拥堵", QColor("#ef4444")),
        ("卡住", QColor("#f97316")),
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
