from __future__ import annotations

from math import ceil
from typing import Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from utils.fonts import ui_font


class CanvasWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(900, 620)
        self.frame: dict | None = None
        self.show_paths = False

    def set_frame(self, frame: dict) -> None:
        self.frame = frame
        self.update()

    def set_show_paths(self, show_paths: bool) -> None:
        self.show_paths = show_paths
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#edf2f7"))

        if not self.frame:
            self._draw_empty_scene(painter)
            return

        frame_width, frame_height = self._frame_size()
        scale = min(self.width() / frame_width, self.height() / frame_height)
        x_offset = (self.width() - frame_width * scale) / 2
        y_offset = (self.height() - frame_height * scale) / 2
        painter.translate(x_offset, y_offset)
        painter.scale(scale, scale)

        self._draw_floor(painter)
        if self.show_paths:
            self._draw_path_debug(painter)
        self._draw_door(painter)
        self._draw_exit(painter)
        self._draw_tray_return_points(painter)
        self._draw_stalls(painter)
        self._draw_tables(painter)
        self._draw_students(painter)
        self._draw_header(painter)

    def _draw_empty_scene(self, painter: QPainter) -> None:
        painter.setPen(QColor("#475569"))
        painter.setFont(ui_font(14))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "点击开始仿真")

    def _draw_floor(self, painter: QPainter) -> None:
        width, height = self._frame_size()
        painter.setPen(QPen(QColor("#dbe4cf"), 1))
        for x in range(0, int(width) + 1, 56):
            painter.drawLine(x, 0, x, int(height))
        for y in range(0, int(height) + 1, 56):
            painter.drawLine(0, y, int(width), y)

        painter.setPen(QPen(QColor("#cbd8be"), 1.4))
        painter.setBrush(QColor("#edf4e8"))
        painter.drawRoundedRect(QRectF(18, 18, width - 36, height - 36), 12, 12)

    def _draw_path_debug(self, painter: QPainter) -> None:
        painter.setFont(ui_font(8, QFont.Weight.Bold))
        colors = {
            "queue": QColor("#2563eb"),
            "top": QColor("#0891b2"),
            "bottom": QColor("#16a34a"),
            "aisle": QColor("#64748b"),
            "door": QColor("#1d4ed8"),
            "exit": QColor("#15803d"),
        }
        for path in self.frame.get("walk_paths", []):
            if not isinstance(path, dict):
                continue
            points = path.get("points") or []
            if len(points) < 2:
                continue
            color = colors.get(path.get("kind"), QColor("#475569"))
            pen = QPen(color, 3)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            for start, end in zip(points, points[1:]):
                start_point = self._point(start)
                end_point = self._point(end)
                if start_point is None or end_point is None:
                    continue
                painter.drawLine(
                    int(start_point[0]),
                    int(start_point[1]),
                    int(end_point[0]),
                    int(end_point[1]),
                )

        painter.setPen(QPen(QColor("#db2777"), 2))
        for student in self.frame.get("students", []):
            if not isinstance(student, dict):
                continue
            student_point = self._point((student.get("x"), student.get("y")))
            if student_point is None:
                continue
            points = [student_point, *(student.get("path") or [])]
            if len(points) < 2:
                continue
            for start, end in zip(points, points[1:]):
                start_point = self._point(start)
                end_point = self._point(end)
                if start_point is None or end_point is None:
                    continue
                painter.drawLine(
                    int(start_point[0]),
                    int(start_point[1]),
                    int(end_point[0]),
                    int(end_point[1]),
                )

    def _draw_header(self, painter: QPainter) -> None:
        frame_width, frame_height = self._frame_size()
        game_time = self._number(self.frame.get("game_time"), 0.0)
        duration = self._number(self.frame.get("duration"), 0.0)
        minutes = int(game_time // 60)
        seconds = int(game_time % 60)
        total_minutes = int(duration // 60)

        painter.setPen(QColor("#0f172a"))
        painter.setFont(ui_font(12, QFont.Weight.Bold))
        text = (
            f"仿真 {minutes:02d}:{seconds:02d} / {total_minutes:02d}:00    "
            f"场内 {self._display_value(self.frame.get('active_students'))}    "
            f"已生成 {self._display_value(self.frame.get('spawned_students'))}    "
            f"已离场 {self._display_value(self.frame.get('served_students'))}"
        )
        painter.drawText(QRectF(28, frame_height - 38, frame_width - 56, 30), Qt.AlignmentFlag.AlignLeft, text)

    def _draw_door(self, painter: QPainter) -> None:
        point = self._point(self.frame.get("door"))
        if point is None:
            return
        x, y = point
        painter.setPen(QPen(QColor("#1f2937"), 2))
        painter.setBrush(QColor("#dbeafe"))
        painter.drawRoundedRect(QRectF(x - 36, y - 36, 72, 72), 6, 6)
        painter.setFont(ui_font(11, QFont.Weight.Bold))
        painter.setPen(QColor("#1d4ed8"))
        painter.drawText(QRectF(x - 34, y - 10, 68, 28), Qt.AlignmentFlag.AlignCenter, "大门")

    def _draw_exit(self, painter: QPainter) -> None:
        point = self._point(self.frame.get("exit"))
        if point is None:
            return
        x, y = point
        painter.setPen(QPen(QColor("#166534"), 2))
        painter.setBrush(QColor("#dcfce7"))
        painter.drawRoundedRect(QRectF(x - 58, y - 58, 116, 116), 8, 8)
        painter.setFont(ui_font(11, QFont.Weight.Bold))
        painter.setPen(QColor("#15803d"))
        painter.drawText(QRectF(x - 34, y - 10, 68, 28), Qt.AlignmentFlag.AlignCenter, "出口")

    def _draw_stalls(self, painter: QPainter) -> None:
        painter.setFont(ui_font(8))
        for stall in self.frame.get("stalls", []):
            if not isinstance(stall, dict):
                continue
            point = self._point((stall.get("x"), stall.get("y")))
            if point is None:
                continue
            x, y = point
            self._draw_cook_timer(painter, stall)
            painter.setPen(QPen(QColor("#334155"), 1.5))
            painter.setBrush(QColor("#fff7ed"))
            painter.drawRoundedRect(QRectF(x - 38, y - 26, 76, 48), 6, 6)

            stall_id = int(self._number(stall.get("id"), 0))
            painter.setPen(QColor("#7c2d12"))
            painter.drawText(QRectF(x - 32, y - 22, 64, 16), Qt.AlignmentFlag.AlignCenter, f"W{stall_id + 1}")
            self._draw_chef_pig(painter, x, y + 2)

            queue_count = int(self._number(stall.get("queue_count"), 0))
            painter.setPen(QColor("#475569"))
            painter.drawText(QRectF(x - 28, y + 4, 56, 18), Qt.AlignmentFlag.AlignCenter, f"排队 {queue_count}")

            painter.setPen(QPen(QColor("#cbd5e1"), 1))
            queue_x = x
            for index in range(min(queue_count, 9)):
                queue_y = y + 76 + index * 24
                painter.drawEllipse(QRectF(queue_x - 6, queue_y - 6, 12, 12))

    def _draw_cook_timer(self, painter: QPainter, stall: dict) -> None:
        point = self._point((stall.get("x"), stall.get("y")))
        if point is None:
            return
        x, y = point
        progress = max(0.0, min(1.0, self._number(stall.get("cook_progress"), 0.0)))
        remaining = self._number(stall.get("cook_remaining"), 0.0)
        painter.setPen(QPen(QColor("#64748b"), 1))
        painter.setBrush(QColor("#f1f5f9"))
        painter.drawRoundedRect(QRectF(x - 35, y - 43, 70, 9), 3, 3)
        if progress > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#f59e0b"))
            painter.drawRoundedRect(QRectF(x - 34, y - 42, 68 * progress, 7), 3, 3)
            painter.setPen(QColor("#92400e"))
            painter.setFont(ui_font(7))
            painter.drawText(QRectF(x - 22, y - 58, 44, 14), Qt.AlignmentFlag.AlignCenter, f"{ceil(remaining)}s")

    def _draw_chef_pig(self, painter: QPainter, x: float, y: float) -> None:
        painter.setPen(QPen(QColor("#9a3412"), 1.1))
        painter.setBrush(QColor("#fda4af"))
        painter.drawEllipse(QRectF(x - 11, y - 8, 22, 18))
        painter.drawEllipse(QRectF(x - 13, y - 11, 7, 7))
        painter.drawEllipse(QRectF(x + 6, y - 11, 7, 7))
        painter.setBrush(QColor("#fecdd3"))
        painter.drawEllipse(QRectF(x - 6, y - 1, 12, 7))
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#94a3b8"), 1))
        painter.drawRoundedRect(QRectF(x - 12, y - 19, 24, 8), 3, 3)
        painter.drawEllipse(QRectF(x - 9, y - 24, 8, 8))
        painter.drawEllipse(QRectF(x - 2, y - 26, 8, 8))
        painter.drawEllipse(QRectF(x + 5, y - 24, 8, 8))
        painter.setPen(QPen(QColor("#831843"), 1.1))
        painter.drawPoint(int(x - 4), int(y - 4))
        painter.drawPoint(int(x + 4), int(y - 4))

    def _draw_tables(self, painter: QPainter) -> None:
        for table in self.frame.get("tables", []):
            if not isinstance(table, dict):
                continue
            point = self._point((table.get("x"), table.get("y")))
            if point is None:
                continue
            x, y = point
            painter.setPen(QPen(QColor("#475569"), 1.2))
            painter.setBrush(QColor("#fef3c7"))
            painter.drawRoundedRect(QRectF(x - 25, y - 17, 50, 34), 5, 5)

            seat_offsets = [(-34, -28), (26, -28), (-34, 20), (26, 20)]
            seats = table.get("seat_frames") or table.get("seats") or []
            for index, (dx, dy) in enumerate(seat_offsets):
                seat = seats[index] if index < len(seats) else None
                status = self._seat_status(seat)
                painter.setBrush(self._seat_color(status))
                painter.setPen(QPen(QColor("#64748b"), 1))
                painter.drawEllipse(QRectF(x + dx, y + dy, 16, 16))

    def _draw_students(self, painter: QPainter) -> None:
        for student in self.frame.get("students", []):
            if not isinstance(student, dict):
                continue
            self._draw_pig(painter, student)

    def _draw_pig(self, painter: QPainter, student: dict) -> None:
        point = self._point((student.get("x"), student.get("y")))
        if point is None:
            return
        x, y = point
        state = str(student.get("state") or "unknown")
        outline = QColor("#be185d")
        fill = self._student_fill_color(state)

        painter.setPen(QPen(outline, 1.4))
        painter.setBrush(fill)
        painter.drawEllipse(QRectF(x - 12, y - 10, 24, 22))

        painter.setBrush(fill.lighter(105))
        painter.drawEllipse(QRectF(x - 15, y - 13, 8, 8))
        painter.drawEllipse(QRectF(x + 7, y - 13, 8, 8))

        painter.setBrush(QColor("#fecdd3"))
        painter.drawEllipse(QRectF(x - 7, y - 2, 14, 9))

        painter.setBrush(QColor("#9f1239"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(x - 4, y + 1, 2.5, 2.5))
        painter.drawEllipse(QRectF(x + 2, y + 1, 2.5, 2.5))

        painter.setPen(QPen(QColor("#831843"), 1.2))
        painter.drawPoint(int(x - 5), int(y - 4))
        painter.drawPoint(int(x + 5), int(y - 4))
        self._draw_student_expression(painter, x, y, state)

    def _draw_student_expression(self, painter: QPainter, x: float, y: float, state: str) -> None:
        painter.setFont(ui_font(8, QFont.Weight.Bold))
        if state == "deciding":
            painter.setPen(QColor("#7c3aed"))
            painter.drawText(QRectF(x + 8, y - 24, 16, 16), Qt.AlignmentFlag.AlignCenter, "?")
            painter.setPen(QPen(QColor("#831843"), 1.1))
            painter.drawLine(int(x - 4), int(y + 8), int(x + 4), int(y + 8))
        elif state in ("leaving", "done"):
            painter.setPen(QPen(QColor("#831843"), 1.2))
            painter.drawArc(QRectF(x - 6, y + 2, 12, 9), 200 * 16, 140 * 16)
            painter.setPen(QColor("#15803d"))
            painter.drawText(QRectF(x - 13, y + 11, 26, 14), Qt.AlignmentFlag.AlignCenter, "离")
        elif state == "eating":
            painter.setPen(QPen(QColor("#831843"), 1.1))
            painter.drawArc(QRectF(x - 5, y + 4, 10, 7), 200 * 16, 140 * 16)
        elif state == "searching_seat":
            painter.setPen(QColor("#0f766e"))
            painter.drawText(QRectF(x + 8, y - 24, 20, 16), Qt.AlignmentFlag.AlignCenter, "座?")
        elif state in ("moving_to_seat", "moving_to_table"):
            painter.setPen(QColor("#0369a1"))
            painter.drawText(QRectF(x + 8, y - 24, 18, 16), Qt.AlignmentFlag.AlignCenter, "座")
        elif state == "moving_to_tray_return":
            painter.setPen(QColor("#0f766e"))
            painter.drawText(QRectF(x + 8, y - 24, 18, 16), Qt.AlignmentFlag.AlignCenter, "收")
        elif state == "waiting_seat":
            painter.setPen(QColor("#ea580c"))
            painter.drawText(QRectF(x + 8, y - 24, 18, 16), Qt.AlignmentFlag.AlignCenter, "等")
        else:
            painter.setPen(QPen(QColor("#831843"), 1.1))
            painter.drawArc(QRectF(x - 6, y + 6, 12, 8), 20 * 16, 140 * 16)

    def _draw_tray_return_points(self, painter: QPainter) -> None:
        for point in self.frame.get("tray_return_points", []):
            rect = self._rect_frame(point, default_width=120.0, default_height=70.0)
            if rect is None:
                continue
            x, y, width, height, congested = rect
            painter.setPen(QPen(QColor("#0f766e" if not congested else "#b45309"), 2))
            painter.setBrush(QColor("#ccfbf1" if not congested else "#fed7aa"))
            painter.drawRoundedRect(QRectF(x - width / 2, y - height / 2, width, height), 8, 8)
            painter.setFont(ui_font(9, QFont.Weight.Bold))
            painter.setPen(QColor("#115e59" if not congested else "#9a3412"))
            painter.drawText(QRectF(x - width / 2, y - 9, width, 20), Qt.AlignmentFlag.AlignCenter, "餐盘回收")

    def _draw_stats_panel(self, painter: QPainter) -> None:
        stats = self.frame.get("stats") or {}
        if not isinstance(stats, dict):
            stats = {}

        frame_width, _ = self._frame_size()
        panel_width = 250.0
        x = max(24.0, frame_width - panel_width - 24.0)
        y = 270.0
        queue_stats = stats.get("stall_queue_stats") or []
        queue_items = [
            f"W{int(self._number(item.get('stall_id'), 0)) + 1}: {self._display_value(item.get('max_queue_length'))}"
            for item in queue_stats
            if isinstance(item, dict)
        ]
        queue_lines = [
            "    ".join(queue_items[index : index + 2])
            for index in range(0, len(queue_items), 2)
        ]
        line_count = 7 + len(queue_lines)
        panel_height = 30.0 + line_count * 20.0

        painter.setPen(QPen(QColor("#334155"), 1))
        painter.setBrush(QColor(255, 255, 255, 225))
        painter.drawRoundedRect(QRectF(x, y, panel_width, panel_height), 8, 8)

        painter.setFont(ui_font(10, QFont.Weight.Bold))
        painter.setPen(QColor("#0f172a"))
        painter.drawText(QRectF(x + 12, y + 8, panel_width - 24, 20), Qt.AlignmentFlag.AlignLeft, "P0 统计")

        painter.setFont(ui_font(8))
        lines = [
            f"avg_wait_time: {self._format_seconds(stats.get('avg_wait_time'))}",
            f"avg_total_time: {self._format_seconds(stats.get('avg_total_time'))}",
            f"max_active_students: {self._display_value(stats.get('max_active_students'))}",
            f"seat_utilization: {self._format_percent(stats.get('seat_utilization'))}",
            "stall_queue_stats.max_queue_length:",
            *(f"  {line}" for line in queue_lines),
        ]
        if not queue_lines:
            lines.append("  -")
        text_y = y + 34.0
        for line in lines:
            painter.drawText(QRectF(x + 12, text_y, panel_width - 24, 18), Qt.AlignmentFlag.AlignLeft, line)
            text_y += 20.0

    def _frame_size(self) -> tuple[float, float]:
        if not self.frame:
            return 1280.0, 800.0
        width = self._number(self.frame.get("width"), 1280.0)
        height = self._number(self.frame.get("height"), 800.0)
        return max(1.0, width), max(1.0, height)

    def _point(self, value: Any) -> tuple[float, float] | None:
        if isinstance(value, dict):
            x = value.get("x")
            y = value.get("y")
        elif isinstance(value, (tuple, list)) and len(value) >= 2:
            x, y = value[0], value[1]
        else:
            return None
        try:
            return float(x), float(y)
        except (TypeError, ValueError):
            return None

    def _rect_frame(
        self,
        value: Any,
        default_width: float,
        default_height: float,
    ) -> tuple[float, float, float, float, bool] | None:
        if isinstance(value, dict):
            point = self._point(value)
            width = self._number(value.get("width"), default_width)
            height = self._number(value.get("height"), default_height)
            congested = bool(value.get("is_congested", False))
        elif isinstance(value, (tuple, list)) and len(value) >= 2:
            point = self._point(value)
            width = self._number(value[2], default_width) if len(value) >= 3 else default_width
            height = self._number(value[3], default_height) if len(value) >= 4 else default_height
            congested = False
        else:
            return None
        if point is None:
            return None
        return point[0], point[1], max(1.0, width), max(1.0, height), congested

    def _seat_status(self, seat: Any) -> str:
        if isinstance(seat, dict):
            status = seat.get("status")
            if status:
                return str(status)
            return "occupied" if seat.get("student_id") is not None else "free"
        return "occupied" if seat is not None else "free"

    def _seat_color(self, status: str) -> QColor:
        if status == "reserved":
            return QColor("#fbbf24")
        if status == "occupied":
            return QColor("#fb7185")
        return QColor("#e2e8f0")

    def _student_fill_color(self, state: str) -> QColor:
        colors = {
            "deciding": QColor("#e9d5ff"),
            "moving_to_queue": QColor("#bfdbfe"),
            "queued": QColor("#fbcfe8"),
            "searching_seat": QColor("#99f6e4"),
            "waiting_seat": QColor("#fed7aa"),
            "moving_to_table": QColor("#fda4af"),
            "moving_to_seat": QColor("#bae6fd"),
            "eating": QColor("#fb7185"),
            "moving_to_tray_return": QColor("#5eead4"),
            "leaving": QColor("#fecdd3"),
            "done": QColor("#bbf7d0"),
        }
        return colors.get(state, QColor("#f9a8d4"))

    def _format_seconds(self, value: Any) -> str:
        if value is None:
            return "-"
        seconds = self._number(value, None)
        if seconds is None:
            return "-"
        minutes = int(seconds // 60)
        remaining = int(round(seconds % 60))
        if minutes <= 0:
            return f"{remaining}s"
        return f"{minutes}m {remaining:02d}s"

    def _format_percent(self, value: Any) -> str:
        if value is None:
            return "-"
        number = self._number(value, None)
        if number is None:
            return "-"
        return f"{number * 100:.1f}%"

    def _display_value(self, value: Any) -> str:
        if value is None:
            return "-"
        return str(value)

    def _number(self, value: Any, default: float | None) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
