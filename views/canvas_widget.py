from __future__ import annotations

from math import ceil
from typing import Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QLinearGradient, QRadialGradient
from PyQt6.QtWidgets import QWidget


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
        
        # Base ambient background color
        painter.fillRect(self.rect(), QColor("#cbd5e1"))

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
        painter.setFont(QFont("Microsoft YaHei UI", 16, QFont.Weight.Bold))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "✨ 点击开始仿真 ✨")

    def _draw_floor(self, painter: QPainter) -> None:
        width, height = self._frame_size()
        
        # Premium background
        bg_gradient = QLinearGradient(0, 0, width, height)
        bg_gradient.setColorAt(0.0, QColor("#f8fafc"))
        bg_gradient.setColorAt(1.0, QColor("#e2e8f0"))
        painter.setBrush(bg_gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(4, 4, width - 8, height - 8), 16, 16)

        # Draw elegant grid tiles
        painter.setPen(QPen(QColor(255, 255, 255, 180), 1.5))
        for x in range(24, int(width) - 4, 60):
            painter.drawLine(x, 4, x, int(height) - 4)
        for y in range(24, int(height) - 4, 60):
            painter.drawLine(4, y, int(width) - 4, y)

        # Draw canteen boundary with a subtle 3D rim
        painter.setPen(QPen(QColor("#94a3b8"), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(4, 4, width - 8, height - 8), 16, 16)

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

        # Glassmorphism panel at the top center
        panel_width = 540
        panel_height = 40
        x = (frame_width - panel_width) / 2
        y = 4
        
        # Shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 25))
        painter.drawRoundedRect(QRectF(x + 2, y + 4, panel_width, panel_height), 20, 20)

        # Glass background
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.setPen(QPen(QColor(255, 255, 255, 255), 1.5))
        painter.drawRoundedRect(QRectF(x, y, panel_width, panel_height), 20, 20)

        painter.setPen(QColor("#0f172a"))
        painter.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.Bold))
        text = (
            f"⏱️ {minutes:02d}:{seconds:02d} / {total_minutes:02d}:00    "
            f"👤 场内: {self._display_value(self.frame.get('active_students'))}    "
            f"✨ 生成: {self._display_value(self.frame.get('spawned_students'))}    "
            f"✅ 离场: {self._display_value(self.frame.get('served_students'))}"
        )
        painter.drawText(QRectF(x, y, panel_width, panel_height), Qt.AlignmentFlag.AlignCenter, text)

    def _draw_door(self, painter: QPainter) -> None:
        point = self._point(self.frame.get("door"))
        if point is None:
            return
        x, y = point
        
        # Shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 35))
        painter.drawRoundedRect(QRectF(x - 34, y - 34, 72, 72), 12, 12)

        # Portal effect
        gradient = QRadialGradient(x, y, 40)
        gradient.setColorAt(0.0, QColor("#60a5fa"))
        gradient.setColorAt(1.0, QColor("#3b82f6"))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor("#1e3a8a"), 2.5))
        painter.drawRoundedRect(QRectF(x - 36, y - 36, 72, 72), 12, 12)
        
        # Inner detail
        painter.setPen(QPen(QColor(255, 255, 255, 180), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(x - 30, y - 30, 60, 60), 8, 8)

        painter.setFont(QFont("Microsoft YaHei UI", 13, QFont.Weight.ExtraBold))
        painter.setPen(QColor("#ffffff"))
        painter.drawText(QRectF(x - 34, y - 12, 68, 28), Qt.AlignmentFlag.AlignCenter, "入口")

    def _draw_exit(self, painter: QPainter) -> None:
        point = self._point(self.frame.get("exit"))
        if point is None:
            return
        x, y = point
        
        # Shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 35))
        painter.drawRoundedRect(QRectF(x - 56, y - 56, 116, 116), 16, 16)

        gradient = QRadialGradient(x, y, 65)
        gradient.setColorAt(0.0, QColor("#34d399"))
        gradient.setColorAt(1.0, QColor("#10b981"))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor("#064e3b"), 2.5))
        painter.drawRoundedRect(QRectF(x - 58, y - 58, 116, 116), 16, 16)
        
        # Inner detail
        painter.setPen(QPen(QColor(255, 255, 255, 180), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(x - 48, y - 48, 96, 96), 12, 12)

        painter.setFont(QFont("Microsoft YaHei UI", 15, QFont.Weight.ExtraBold))
        painter.setPen(QColor("#ffffff"))
        painter.drawText(QRectF(x - 34, y - 15, 68, 30), Qt.AlignmentFlag.AlignCenter, "出口")

    def _draw_stalls(self, painter: QPainter) -> None:
        painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold))
        for stall in self.frame.get("stalls", []):
            if not isinstance(stall, dict):
                continue
            point = self._point((stall.get("x"), stall.get("y")))
            if point is None:
                continue
            x, y = point
            
            # Shadow
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 40))
            painter.drawRoundedRect(QRectF(x - 36, y - 24, 76, 48), 6, 6)

            # Stall body
            stall_grad = QLinearGradient(x, y - 26, x, y + 22)
            stall_grad.setColorAt(0.0, QColor("#ffffff"))
            stall_grad.setColorAt(1.0, QColor("#f1f5f9"))
            painter.setPen(QPen(QColor("#64748b"), 2.5))
            painter.setBrush(stall_grad)
            painter.drawRoundedRect(QRectF(x - 38, y - 26, 76, 48), 6, 6)
            
            # Counter top
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#e2e8f0"))
            painter.drawRect(QRectF(x - 37, y + 6, 74, 15))
            painter.setPen(QPen(QColor("#cbd5e1"), 1.5))
            painter.drawLine(int(x - 37), int(y + 6), int(x + 37), int(y + 6))

            # Awning (striped canopy)
            stripe_w = 12.66
            painter.setPen(Qt.PenStyle.NoPen)
            for i in range(6):
                px = x - 38 + i * stripe_w
                painter.setBrush(QColor("#ef4444") if i % 2 == 0 else QColor("#ffffff"))
                painter.drawRect(QRectF(px, y - 30, stripe_w, 18))
                # Awning scallops
                painter.drawEllipse(QRectF(px, y - 18, stripe_w, 10))
            
            # Awning trim
            painter.setPen(QPen(QColor("#991b1b"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(x - 38, y - 30, 76, 18), 2, 2)

            stall_id = int(self._number(stall.get("id"), 0))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRectF(x - 32, y - 28, 64, 16), Qt.AlignmentFlag.AlignCenter, f"W{stall_id + 1}")
            
            self._draw_chef_pig(painter, x, y - 2)

            # Queue
            queue_count = int(self._number(stall.get("queue_count"), 0))
            painter.setPen(QColor("#334155"))
            painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Weight.Bold))
            painter.drawText(QRectF(x - 28, y + 26, 56, 18), Qt.AlignmentFlag.AlignCenter, f"排队 {queue_count}")

            # Elegant queue dots
            painter.setPen(QPen(QColor("#94a3b8"), 1.5))
            queue_x = x
            for index in range(min(queue_count, 9)):
                queue_y = y + 54 + index * 20
                painter.setBrush(QColor("#e2e8f0"))
                painter.drawEllipse(QRectF(queue_x - 6, queue_y - 6, 12, 12))
                
            self._draw_cook_timer(painter, stall)

    def _draw_cook_timer(self, painter: QPainter, stall: dict) -> None:
        point = self._point((stall.get("x"), stall.get("y")))
        if point is None:
            return
        x, y = point
        progress = max(0.0, min(1.0, self._number(stall.get("cook_progress"), 0.0)))
        remaining = self._number(stall.get("cook_remaining"), 0.0)
        
        # Shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 20))
        painter.drawRoundedRect(QRectF(x - 38, y - 46, 76, 12), 6, 6)

        painter.setPen(QPen(QColor("#94a3b8"), 1.5))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(QRectF(x - 40, y - 48, 80, 12), 6, 6)
        
        if progress > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            
            bar_grad = QLinearGradient(x - 38, y - 46, x - 38 + 76 * progress, y - 46)
            bar_grad.setColorAt(0.0, QColor("#34d399"))
            bar_grad.setColorAt(1.0, QColor("#10b981") if progress > 0.5 else QColor("#fbbf24"))
            
            painter.setBrush(bar_grad)
            painter.drawRoundedRect(QRectF(x - 38, y - 46, 76 * progress, 8), 4, 4)
            
            painter.setPen(QColor("#0f172a"))
            painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.Weight.Bold))
            painter.drawText(QRectF(x - 22, y - 64, 44, 14), Qt.AlignmentFlag.AlignCenter, f"{ceil(remaining)}s")

    def _draw_chef_pig(self, painter: QPainter, x: float, y: float) -> None:
        # Pig body
        painter.setPen(QPen(QColor("#9a3412"), 1.8))
        grad = QRadialGradient(x, y, 15)
        grad.setColorAt(0.0, QColor("#fecdd3"))
        grad.setColorAt(1.0, QColor("#fda4af"))
        painter.setBrush(grad)
        painter.drawEllipse(QRectF(x - 13, y - 10, 26, 22))
        
        # Ears
        painter.setBrush(QColor("#fda4af"))
        painter.drawEllipse(QRectF(x - 15, y - 13, 8, 8))
        painter.drawEllipse(QRectF(x + 7, y - 13, 8, 8))
        
        # Snout
        painter.setBrush(QColor("#fecdd3"))
        painter.setPen(QPen(QColor("#be185d"), 1.2))
        painter.drawEllipse(QRectF(x - 7, y - 1, 14, 8))
        
        # Chef Hat
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#94a3b8"), 1.8))
        painter.drawRoundedRect(QRectF(x - 14, y - 22, 28, 10), 4, 4)
        painter.drawEllipse(QRectF(x - 12, y - 28, 10, 10))
        painter.drawEllipse(QRectF(x - 4, y - 31, 10, 10))
        painter.drawEllipse(QRectF(x + 4, y - 28, 10, 10))
        
        # Eyes
        painter.setPen(QPen(QColor("#4c0519"), 2))
        painter.drawPoint(int(x - 5), int(y - 5))
        painter.drawPoint(int(x + 5), int(y - 5))

    def _draw_tables(self, painter: QPainter) -> None:
        for table in self.frame.get("tables", []):
            if not isinstance(table, dict):
                continue
            point = self._point((table.get("x"), table.get("y")))
            if point is None:
                continue
            x, y = point
            
            tx, ty = x + 4, y + 4
            
            # Table shadow
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 45))
            painter.drawRoundedRect(QRectF(tx - 23, ty - 15, 50, 34), 6, 6)

            # Premium Wooden Table top
            table_gradient = QLinearGradient(tx - 25, ty - 17, tx + 25, ty + 17)
            table_gradient.setColorAt(0.0, QColor("#fcd34d"))
            table_gradient.setColorAt(1.0, QColor("#f59e0b"))
            painter.setPen(QPen(QColor("#b45309"), 2))
            painter.setBrush(table_gradient)
            painter.drawRoundedRect(QRectF(tx - 25, ty - 17, 50, 34), 6, 6)
            
            # Subtle highlight
            painter.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(tx - 23, ty - 15, 46, 30), 4, 4)

            seat_offsets = [(-34, -28), (26, -28), (-34, 20), (26, 20)]
            seats = table.get("seat_frames") or table.get("seats") or []
            for index, (dx, dy) in enumerate(seat_offsets):
                seat = seats[index] if index < len(seats) else None
                status = self._seat_status(seat)
                
                cx, cy = x + dx, y + dy
                # Seat shadow
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, 35))
                painter.drawEllipse(QRectF(cx + 1, cy + 2, 16, 16))
                
                # Seat cushion
                seat_color, border_color = self._seat_color(status)
                seat_grad = QRadialGradient(cx + 8, cy + 8, 10)
                seat_grad.setColorAt(0.0, seat_color.lighter(115))
                seat_grad.setColorAt(1.0, seat_color)
                
                painter.setBrush(seat_grad)
                painter.setPen(QPen(border_color, 1.8))
                painter.drawEllipse(QRectF(cx, cy, 16, 16))

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
        fill_color, border_color = self._student_fill_color(state)

        # Soft drop shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 45))
        painter.drawEllipse(QRectF(x - 12, y - 4, 24, 16))

        # Body gradient
        body_grad = QRadialGradient(x - 4, y - 6, 20)
        body_grad.setColorAt(0.0, fill_color.lighter(120))
        body_grad.setColorAt(1.0, fill_color)

        painter.setPen(QPen(border_color, 2))
        painter.setBrush(body_grad)
        painter.drawEllipse(QRectF(x - 14, y - 12, 28, 26))

        # Ears
        painter.setBrush(fill_color.lighter(110))
        painter.drawEllipse(QRectF(x - 16, y - 16, 10, 10))
        painter.drawEllipse(QRectF(x + 6, y - 16, 10, 10))

        # Snout (nose)
        snout_grad = QLinearGradient(x - 8, y - 2, x + 8, y + 8)
        snout_grad.setColorAt(0.0, QColor("#fecdd3"))
        snout_grad.setColorAt(1.0, QColor("#fda4af"))
        painter.setBrush(snout_grad)
        painter.setPen(QPen(border_color.darker(110), 1.5))
        painter.drawEllipse(QRectF(x - 8, y - 2, 16, 11))

        # Nostrils
        painter.setBrush(border_color.darker(130))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(x - 4, y + 2, 3, 3))
        painter.drawEllipse(QRectF(x + 1, y + 2, 3, 3))

        # Eyes
        painter.setPen(QPen(QColor("#4c0519"), 2))
        painter.drawPoint(int(x - 6), int(y - 5))
        painter.drawPoint(int(x + 6), int(y - 5))
        
        # Blush
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 100, 150, 90))
        painter.drawEllipse(QRectF(x - 12, y - 2, 5, 4))
        painter.drawEllipse(QRectF(x + 7, y - 2, 5, 4))

        self._draw_student_expression(painter, x, y, state)

    def _draw_student_expression(self, painter: QPainter, x: float, y: float, state: str) -> None:
        painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Weight.ExtraBold))
        
        # Expression bubble background for readability
        def draw_bubble(cx, cy, text, bg_color, text_color):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(QRectF(cx - 2, cy - 13, len(text) * 11 + 6, 18), 4, 4)
            painter.setPen(text_color)
            painter.drawText(QRectF(cx, cy - 14, len(text) * 11 + 2, 18), Qt.AlignmentFlag.AlignCenter, text)

        if state == "deciding":
            draw_bubble(x + 6, y - 20, "?", QColor(255, 255, 255, 200), QColor("#7c3aed"))
            painter.setPen(QPen(QColor("#831843"), 1.5))
            painter.drawLine(int(x - 4), int(y + 8), int(x + 4), int(y + 8))
        elif state in ("leaving", "done"):
            painter.setPen(QPen(QColor("#831843"), 1.8))
            painter.drawArc(QRectF(x - 6, y + 2, 12, 9), 200 * 16, 140 * 16)
            draw_bubble(x - 22, y + 20, "离", QColor(255, 255, 255, 200), QColor("#15803d"))
        elif state == "eating":
            painter.setPen(QPen(QColor("#831843"), 1.8))
            painter.drawArc(QRectF(x - 5, y + 4, 10, 7), 200 * 16, 140 * 16)
        elif state == "searching_seat":
            draw_bubble(x + 6, y - 20, "座?", QColor(255, 255, 255, 200), QColor("#0f766e"))
        elif state in ("moving_to_seat", "moving_to_table"):
            draw_bubble(x + 6, y - 20, "座", QColor(255, 255, 255, 200), QColor("#0369a1"))
        elif state == "moving_to_tray_return":
            draw_bubble(x + 6, y - 20, "收", QColor(255, 255, 255, 200), QColor("#0f766e"))
        elif state == "waiting_seat":
            draw_bubble(x + 6, y - 20, "等", QColor(255, 255, 255, 200), QColor("#ea580c"))
        else:
            painter.setPen(QPen(QColor("#831843"), 1.5))
            painter.drawArc(QRectF(x - 6, y + 6, 12, 8), 20 * 16, 140 * 16)

    def _draw_tray_return_points(self, painter: QPainter) -> None:
        for point in self.frame.get("tray_return_points", []):
            rect = self._rect_frame(point, default_width=140.0, default_height=80.0)
            if rect is None:
                continue
            x, y, width, height, congested = rect
            
            # Shadow
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 35))
            painter.drawRoundedRect(QRectF(x - width / 2 + 3, y - height / 2 + 3, width, height), 12, 12)

            # Metallic look
            grad = QLinearGradient(x - width/2, y - height/2, x + width/2, y + height/2)
            if not congested:
                grad.setColorAt(0.0, QColor("#e0f2fe"))
                grad.setColorAt(1.0, QColor("#bae6fd"))
                border_color = QColor("#0284c7")
                text_color = QColor("#0369a1")
            else:
                grad.setColorAt(0.0, QColor("#ffedd5"))
                grad.setColorAt(1.0, QColor("#fed7aa"))
                border_color = QColor("#c2410c")
                text_color = QColor("#9a3412")

            painter.setPen(QPen(border_color, 2.5))
            painter.setBrush(grad)
            painter.drawRoundedRect(QRectF(x - width / 2, y - height / 2, width, height), 12, 12)
            
            # Inner conveyor belt/sorting area styling
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 15))
            painter.drawRoundedRect(QRectF(x - width / 2 + 10, y - height / 2 + 10, width - 20, height - 20), 8, 8)
            
            painter.setFont(QFont("Microsoft YaHei UI", 12, QFont.Weight.ExtraBold))
            painter.setPen(text_color)
            painter.drawText(QRectF(x - width / 2, y - 14, width, 28), Qt.AlignmentFlag.AlignCenter, "♻️ 餐盘回收处")

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

        # Shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 20))
        painter.drawRoundedRect(QRectF(x + 2, y + 4, panel_width, panel_height), 12, 12)

        painter.setPen(QPen(QColor("#94a3b8"), 1.5))
        painter.setBrush(QColor(255, 255, 255, 240))
        painter.drawRoundedRect(QRectF(x, y, panel_width, panel_height), 12, 12)

        painter.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.ExtraBold))
        painter.setPen(QColor("#0f172a"))
        painter.drawText(QRectF(x + 16, y + 10, panel_width - 32, 22), Qt.AlignmentFlag.AlignLeft, "📊 P0 统计")

        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.setPen(QColor("#334155"))
        lines = [
            f"平均等待: {self._format_seconds(stats.get('avg_wait_time'))}",
            f"平均总时: {self._format_seconds(stats.get('avg_total_time'))}",
            f"峰值人数: {self._display_value(stats.get('max_active_students'))}",
            f"座位利用: {self._format_percent(stats.get('seat_utilization'))}",
            "各窗口最大排队:",
            *(f"  {line}" for line in queue_lines),
        ]
        if not queue_lines:
            lines.append("  -")
        text_y = y + 42.0
        for line in lines:
            painter.drawText(QRectF(x + 16, text_y, panel_width - 32, 18), Qt.AlignmentFlag.AlignLeft, line)
            text_y += 22.0

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

    def _seat_color(self, status: str) -> tuple[QColor, QColor]:
        if status == "reserved":
            return QColor("#fef08a"), QColor("#ca8a04")
        if status == "occupied":
            return QColor("#fda4af"), QColor("#e11d48")
        return QColor("#f8fafc"), QColor("#94a3b8")

    def _student_fill_color(self, state: str) -> tuple[QColor, QColor]:
        colors = {
            "deciding": (QColor("#e9d5ff"), QColor("#9333ea")),
            "moving_to_queue": (QColor("#bfdbfe"), QColor("#2563eb")),
            "queued": (QColor("#fbcfe8"), QColor("#db2777")),
            "searching_seat": (QColor("#99f6e4"), QColor("#0d9488")),
            "waiting_seat": (QColor("#fed7aa"), QColor("#ea580c")),
            "moving_to_table": (QColor("#fda4af"), QColor("#e11d48")),
            "moving_to_seat": (QColor("#bae6fd"), QColor("#0284c7")),
            "eating": (QColor("#fb7185"), QColor("#be185d")),
            "moving_to_tray_return": (QColor("#5eead4"), QColor("#0f766e")),
            "leaving": (QColor("#fecdd3"), QColor("#e11d48")),
            "done": (QColor("#bbf7d0"), QColor("#16a34a")),
        }
        return colors.get(state, (QColor("#f9a8d4"), QColor("#be185d")))

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

