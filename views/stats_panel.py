from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class StatsPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(280)
        self.setMaximumWidth(360)

        self.title = QLabel("P0 数据统计")
        self.title.setFont(QFont("Microsoft YaHei UI", 12, QFont.Weight.Bold))
        self.title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["指标", "值"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(220)

        self.chart = StatsChart()

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addWidget(self.table)
        layout.addWidget(self.chart, 1)
        self.setLayout(layout)

        self.setStyleSheet(
            """
            StatsPanel {
                background: #f8fafc;
                border-left: 1px solid #cbd5e1;
            }
            QTableWidget {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                gridline-color: #e2e8f0;
                font: 9pt "Microsoft YaHei UI";
            }
            QHeaderView::section {
                background: #e2e8f0;
                border: 0;
                padding: 5px;
                font-weight: 700;
            }
            QTableWidget::item {
                padding: 5px;
            }
            """
        )
        self.set_frame({})

    def set_frame(self, frame: dict | None) -> None:
        frame = frame or {}
        stats = frame.get("stats") or {}
        if not isinstance(stats, dict):
            stats = {}

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

        self.chart.set_stats(stats)


class StatsChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(260)
        self.stats: dict[str, Any] = {}

    def set_stats(self, stats: dict[str, Any]) -> None:
        self.stats = stats
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        bounds = QRectF(0, 0, self.width() - 1, self.height() - 1)
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(bounds.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)

        painter.setPen(QColor("#0f172a"))
        painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold))
        painter.drawText(QRectF(14, 10, self.width() - 28, 20), Qt.AlignmentFlag.AlignLeft, "窗口最大队列")

        queue_stats = self.stats.get("stall_queue_stats") or []
        values = [
            (
                f"W{int(_number(item.get('stall_id'), 0)) + 1}",
                int(_number(item.get("max_queue_length"), 0)),
            )
            for item in queue_stats
            if isinstance(item, dict)
        ]

        chart_rect = QRectF(18, 44, self.width() - 36, max(90, self.height() - 120))
        if values:
            self._draw_queue_bars(painter, chart_rect, values)
        else:
            painter.setPen(QColor("#64748b"))
            painter.setFont(QFont("Microsoft YaHei UI", 9))
            painter.drawText(chart_rect, Qt.AlignmentFlag.AlignCenter, "暂无队列数据")

        self._draw_utilization(painter)

    def _draw_queue_bars(
        self,
        painter: QPainter,
        rect: QRectF,
        values: list[tuple[str, int]],
    ) -> None:
        max_value = max(1, max(value for _, value in values))
        gap = 5.0
        bar_width = max(8.0, (rect.width() - gap * (len(values) - 1)) / len(values))
        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        painter.drawLine(int(rect.left()), int(rect.bottom()), int(rect.right()), int(rect.bottom()))

        for index, (label, value) in enumerate(values):
            left = rect.left() + index * (bar_width + gap)
            height = 0.0 if value <= 0 else rect.height() * value / max_value
            bar_rect = QRectF(left, rect.bottom() - height, bar_width, height)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#0ea5e9" if value < max_value else "#f59e0b"))
            painter.drawRoundedRect(bar_rect, 3, 3)

            painter.setPen(QColor("#334155"))
            painter.setFont(QFont("Microsoft YaHei UI", 7))
            painter.drawText(QRectF(left - 2, rect.bottom() + 4, bar_width + 4, 14), Qt.AlignmentFlag.AlignCenter, label)
            painter.drawText(QRectF(left - 2, bar_rect.top() - 15, bar_width + 4, 14), Qt.AlignmentFlag.AlignCenter, str(value))

    def _draw_utilization(self, painter: QPainter) -> None:
        value = _number(self.stats.get("seat_utilization"), None)
        label = _format_percent(value)
        left = 18.0
        top = self.height() - 58.0
        width = self.width() - 36.0

        painter.setPen(QColor("#0f172a"))
        painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold))
        painter.drawText(QRectF(left, top - 24, width, 20), Qt.AlignmentFlag.AlignLeft, f"座位利用率 {label}")

        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.setBrush(QColor("#e2e8f0"))
        painter.drawRoundedRect(QRectF(left, top, width, 16), 8, 8)
        if value is None:
            return
        fill_width = max(0.0, min(width, width * value))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#14b8a6"))
        painter.drawRoundedRect(QRectF(left, top, fill_width, 16), 8, 8)


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


def _display_value(value: Any) -> str:
    if value is None:
        return "-"
    return str(value)


def _number(value: Any, default: float | None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
