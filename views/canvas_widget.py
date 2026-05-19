from __future__ import annotations

from math import ceil
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class CanvasWidget(QWidget):
    zoomChanged = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(1024, 640)
        self.frame: dict | None = None
        self.show_paths = False
        self.view_zoom = 1.0
        self._pan_offset = QPointF(0.0, 0.0)
        self._drag_start: QPointF | None = None

    def set_frame(self, frame: dict) -> None:
        self.frame = frame
        self.update()

    def set_show_paths(self, show_paths: bool) -> None:
        self.show_paths = show_paths
        self.update()

    def set_view_zoom(self, zoom: float) -> None:
        zoom = max(0.6, min(1.8, zoom))
        if abs(self.view_zoom - zoom) < 0.001:
            return
        self.view_zoom = zoom
        if self.view_zoom <= 1.0:
            self._pan_offset = QPointF(0.0, 0.0)
        self.zoomChanged.emit(self.view_zoom)
        self.update()

    def reset_view(self) -> None:
        self.view_zoom = 1.0
        self._pan_offset = QPointF(0.0, 0.0)
        self.zoomChanged.emit(self.view_zoom)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f7f8f3"))

        if not self.frame:
            self._draw_empty_scene(painter)
            return

        frame_width, frame_height = self._frame_size()
        base_scale = min(self.width() / frame_width, self.height() / frame_height)
        scale = base_scale * self.view_zoom
        x_offset = (self.width() - frame_width * scale) / 2 + self._pan_offset.x()
        y_offset = (self.height() - frame_height * scale) / 2 + self._pan_offset.y()
        painter.translate(x_offset, y_offset)
        painter.scale(scale, scale)
        self._draw_floor(painter)
        if self.show_paths:
            self._draw_path_debug(painter)
        self._draw_door(painter)
        self._draw_exit(painter)
        self._draw_stalls(painter)
        self._draw_tables(painter)
        self._draw_students(painter)
        self._draw_header(painter)

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                factor = 1.08 if delta > 0 else 1 / 1.08
                self.set_view_zoom(self.view_zoom * factor)
                event.accept()
                return
        super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton) and self.view_zoom > 1.0:
            self._drag_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._drag_start is not None:
            current = event.position()
            delta = current - self._drag_start
            self._drag_start = current
            self._pan_offset = self._pan_offset + delta
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._drag_start is not None and event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._drag_start = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_view()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _draw_empty_scene(self, painter: QPainter) -> None:
        painter.setPen(QColor("#475569"))
        painter.setFont(QFont("Microsoft YaHei UI", 14))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "点击开始仿真")

    def _draw_floor(self, painter: QPainter) -> None:
        width, height = self._frame_size()
        painter.setPen(QPen(QColor("#d7dccd"), 1))
        for x in range(0, int(width) + 1, 56):
            painter.drawLine(x, 0, x, int(height))
        for y in range(0, int(height) + 1, 56):
            painter.drawLine(0, y, int(width), y)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#e9efe0"))
        painter.drawRoundedRect(QRectF(18, 18, width - 36, height - 36), 8, 8)

    def _draw_path_debug(self, painter: QPainter) -> None:
        painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.Weight.Bold))
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
                painter.drawLine(int(start_point[0]), int(start_point[1]), int(end_point[0]), int(end_point[1]))

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
                painter.drawLine(int(start_point[0]), int(start_point[1]), int(end_point[0]), int(end_point[1]))

    def _draw_header(self, painter: QPainter) -> None:
        _, frame_height = self._frame_size()
        game_time = self._number(self.frame.get("game_time"), 0.0)
        duration = self._number(self.frame.get("duration"), 0.0)
        minutes = int(game_time // 60)
        seconds = int(game_time % 60)
        total_minutes = int(duration // 60)

        painter.setPen(QColor("#0f172a"))
        painter.setFont(QFont("Microsoft YaHei UI", 12, QFont.Weight.Bold))
        text = (
            f"仿真 {minutes:02d}:{seconds:02d} / {total_minutes:02d}:00    "
            f"场内 {self._display_value(self.frame.get('active_students'))}    "
            f"已生成 {self._display_value(self.frame.get('spawned_students'))}    "
            f"已离场 {self._display_value(self.frame.get('served_students'))}"
        )
        painter.drawText(QRectF(28, frame_height - 38, 760, 30), Qt.AlignmentFlag.AlignLeft, text)

    def _draw_door(self, painter: QPainter) -> None:
        point = self._point(self.frame.get("door"))
        if point is None:
            return
        x, y = point
        painter.setPen(QPen(QColor("#1f2937"), 2))
        painter.setBrush(QColor("#dbeafe"))
        painter.drawRoundedRect(QRectF(x - 36, y - 36, 72, 72), 6, 6)
        painter.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.Bold))
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
        painter.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.Bold))
        painter.setPen(QColor("#15803d"))
        painter.drawText(QRectF(x - 34, y - 10, 68, 28), Qt.AlignmentFlag.AlignCenter, "出口")

    def _draw_stalls(self, painter: QPainter) -> None:
        painter.setFont(QFont("Microsoft YaHei UI", 8))
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
            self._draw_stall_dishes(painter, stall, x, y)

            painter.setPen(QPen(QColor("#cbd5e1"), 1))
            queue_x = x
            for index in range(min(queue_count, 9)):
                queue_y = y + 76 + index * 24
                painter.drawEllipse(QRectF(queue_x - 6, queue_y - 6, 12, 12))

    def _draw_stall_dishes(self, painter: QPainter, stall: dict, x: float, y: float) -> None:
        dishes = self._stall_dishes(stall)
        if not dishes:
            return

        panel_width = 142.0
        row_height = 20.0
        visible_dishes = dishes[:3]
        panel_height = 22.0 + len(visible_dishes) * row_height
        left = x + 48.0
        top = y - 48.0

        painter.setPen(QPen(QColor(234, 179, 8, 135), 1))
        painter.setBrush(QColor(255, 251, 235, 232))
        painter.drawRoundedRect(QRectF(left, top, panel_width, panel_height), 7, 7)

        painter.setPen(QColor("#854d0e"))
        painter.setFont(QFont("Microsoft YaHei UI", 7, QFont.Weight.Bold))
        painter.drawText(QRectF(left + 8, top + 4, panel_width - 16, 14), Qt.AlignmentFlag.AlignLeft, "菜品 / 价格 / 库存")

        painter.setFont(QFont("Microsoft YaHei UI", 7))
        for index, dish in enumerate(visible_dishes):
            row_top = top + 22.0 + index * row_height
            available = self._dish_available(dish)
            name = str(dish.get("name") or f"菜品{index + 1}")
            name = painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, 50)
            price = self._format_price(dish.get("price"))
            stock = self._display_value(dish.get("stock"))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#dcfce7" if available else "#fee2e2"))
            painter.drawRoundedRect(QRectF(left + 7, row_top + 2, 32, 14), 5, 5)

            painter.setPen(QColor("#166534" if available else "#991b1b"))
            painter.setFont(QFont("Microsoft YaHei UI", 7, QFont.Weight.Bold))
            painter.drawText(QRectF(left + 8, row_top + 1, 30, 15), Qt.AlignmentFlag.AlignCenter, "可售" if available else "售罄")

            painter.setPen(QColor("#334155"))
            painter.setFont(QFont("Microsoft YaHei UI", 7))
            painter.drawText(QRectF(left + 43, row_top + 1, 52, 16), Qt.AlignmentFlag.AlignLeft, name)
            painter.drawText(QRectF(left + 92, row_top + 1, 30, 16), Qt.AlignmentFlag.AlignRight, price)
            painter.drawText(QRectF(left + 124, row_top + 1, 12, 16), Qt.AlignmentFlag.AlignRight, stock)

    def _stall_dishes(self, stall: dict) -> list[dict[str, Any]]:
        raw_dishes = stall.get("dishes")
        if isinstance(raw_dishes, list):
            dishes = [dish for dish in raw_dishes if isinstance(dish, dict)]
            if dishes:
                return dishes
        return self._mock_stall_dishes(stall)

    def _mock_stall_dishes(self, stall: dict) -> list[dict[str, Any]]:
        stall_id = int(self._number(stall.get("id"), 0))
        queue_count = int(self._number(stall.get("queue_count"), 0))
        cook_time = self._number(stall.get("cook_time"), 45.0)
        meat_ratio = max(0.0, min(1.0, self._number(stall.get("meat_ratio"), 0.5)))
        veg_ratio = max(0.0, min(1.0, self._number(stall.get("veg_ratio"), 0.5)))
        base_id = stall_id * 100
        stocks = [
            max(0, 24 - queue_count),
            max(0, 16 - queue_count // 2),
            0 if queue_count >= 8 else max(1, 10 - queue_count // 3),
        ]
        names = ["招牌套餐", "清爽素菜", "今日小炒"]
        prices = [12.0 + stall_id, 8.0 + stall_id * 0.5, 10.0 + stall_id * 0.8]
        return [
            {
                "id": base_id + index + 1,
                "name": name,
                "features": {"meat_ratio": meat_ratio, "veg_ratio": veg_ratio},
                "price": prices[index],
                "stock": stocks[index],
                "cook_time": cook_time,
                "available": stocks[index] > 0,
            }
            for index, name in enumerate(names)
        ]

    def _dish_available(self, dish: dict) -> bool:
        if "available" in dish:
            return bool(dish.get("available"))
        stock = self._number(dish.get("stock"), None)
        if stock is None:
            return True
        return stock > 0

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
            painter.setFont(QFont("Microsoft YaHei UI", 7))
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

            seats = [(-34, -28), (26, -28), (-34, 20), (26, 20)]
            seat_values = table.get("seat_frames") or table.get("seats") or []
            for index, (dx, dy) in enumerate(seats):
                seat = seat_values[index] if index < len(seat_values) else None
                status = self._seat_status(seat)
                painter.setBrush(self._seat_color(status))
                painter.setPen(QPen(QColor("#64748b"), 1))
                painter.drawEllipse(QRectF(x + dx, y + dy, 16, 16))

    def _draw_students(self, painter: QPainter) -> None:
        students = [student for student in self.frame.get("students", []) if isinstance(student, dict)]
        students.sort(key=lambda item: self._number(item.get("y"), 0.0))
        for student in students:
            self._draw_pig(painter, student)

    def _draw_pig(self, painter: QPainter, student: dict) -> None:
        point = self._point((student.get("x"), student.get("y")))
        if point is None:
            return
        x, y = point
        state = str(student.get("state") or "unknown")
        outline = QColor("#be185d")
        fill = QColor("#f9a8d4")
        if state == "queued":
            fill = QColor("#fbcfe8")
        elif state == "eating":
            fill = QColor("#fb7185")
        elif state == "moving_to_table":
            fill = QColor("#fda4af")
        elif state == "leaving":
            fill = QColor("#fecdd3")

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
        painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.Weight.Bold))
        if state == "deciding":
            painter.setPen(QColor("#7c3aed"))
            painter.drawText(QRectF(x + 8, y - 24, 16, 16), Qt.AlignmentFlag.AlignCenter, "?")
            painter.setPen(QPen(QColor("#831843"), 1.1))
            painter.drawLine(int(x - 4), int(y + 8), int(x + 4), int(y + 8))
        elif state in ("leaving", "done"):
            painter.setPen(QPen(QColor("#831843"), 1.2))
            painter.drawArc(QRectF(x - 6, y + 2, 12, 9), 200 * 16, 140 * 16)
            painter.setPen(QColor("#15803d"))
            painter.drawText(QRectF(x - 13, y + 11, 26, 14), Qt.AlignmentFlag.AlignCenter, "饱")
        elif state == "eating":
            painter.setPen(QPen(QColor("#831843"), 1.1))
            painter.drawArc(QRectF(x - 5, y + 4, 10, 7), 200 * 16, 140 * 16)
        else:
            painter.setPen(QPen(QColor("#831843"), 1.1))
            painter.drawArc(QRectF(x - 6, y + 6, 12, 8), 20 * 16, 140 * 16)

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

    def _format_price(self, value: Any) -> str:
        number = self._number(value, None)
        if number is None:
            return "-"
        return f"{number:.1f}"

    def _display_value(self, value: Any) -> str:
        if value is None:
            return "-"
        return str(value)

    def _number(self, value: Any, default: float | None) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
