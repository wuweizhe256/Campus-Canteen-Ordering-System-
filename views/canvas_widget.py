from __future__ import annotations

from math import ceil

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class CanvasWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(1024, 640)
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
        painter.fillRect(self.rect(), QColor("#f7f8f3"))

        if not self.frame:
            self._draw_empty_scene(painter)
            return

        f_width = self.frame.get("width", 1280)
        f_height = self.frame.get("height", 800)
        scale = min(self.width() / f_width, self.height() / f_height)
        x_offset = (self.width() - f_width * scale) / 2
        y_offset = (self.height() - f_height * scale) / 2
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
        self._draw_stats_panel(painter)

    def _draw_empty_scene(self, painter: QPainter) -> None:
        painter.setPen(QColor("#475569"))
        painter.setFont(QFont("Microsoft YaHei UI", 14))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "点击开始仿真")

    def _draw_floor(self, painter: QPainter) -> None:
        width = self.frame.get("width", 1280)
        height = self.frame.get("height", 800)
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
            points = path["points"]
            if len(points) < 2:
                continue
            color = colors.get(path["kind"], QColor("#475569"))
            pen = QPen(color, 3)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            for start, end in zip(points, points[1:]):
                painter.drawLine(int(start[0]), int(start[1]), int(end[0]), int(end[1]))

        painter.setPen(QPen(QColor("#db2777"), 2))
        for student in self.frame.get("students", []):
            points = [(student["x"], student["y"]), *student.get("path", [])]
            if len(points) < 2:
                continue
            for start, end in zip(points, points[1:]):
                painter.drawLine(int(start[0]), int(start[1]), int(end[0]), int(end[1]))

    def _draw_header(self, painter: QPainter) -> None:
        game_time = self.frame.get("game_time", 0)
        duration = self.frame.get("duration", 0)
        minutes = int(game_time // 60)
        seconds = int(game_time % 60)
        total_minutes = int(duration // 60)

        painter.setPen(QColor("#0f172a"))
        painter.setFont(QFont("Microsoft YaHei UI", 12, QFont.Weight.Bold))
        text = (
            f"仿真 {minutes:02d}:{seconds:02d} / {total_minutes:02d}:00    "
            f"场内 {self.frame.get('active_students', 0)}    "
            f"已生成 {self.frame.get('spawned_students', 0)}    "
            f"已离场 {self.frame.get('served_students', 0)}"
        )
        painter.drawText(QRectF(28, self.frame.get("height", 800) - 38, 760, 30), Qt.AlignmentFlag.AlignLeft, text)

    def _draw_door(self, painter: QPainter) -> None:
        door = self.frame.get("door")
        if not door:
            return
        x, y = door
        painter.setPen(QPen(QColor("#1f2937"), 2))
        painter.setBrush(QColor("#dbeafe"))
        painter.drawRoundedRect(QRectF(x - 36, y - 36, 72, 72), 6, 6)
        painter.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.Bold))
        painter.setPen(QColor("#1d4ed8"))
        painter.drawText(QRectF(x - 34, y - 10, 68, 28), Qt.AlignmentFlag.AlignCenter, "大门")

    def _draw_exit(self, painter: QPainter) -> None:
        exit_pos = self.frame.get("exit")
        if not exit_pos:
            return
        x, y = exit_pos
        painter.setPen(QPen(QColor("#166534"), 2))
        painter.setBrush(QColor("#dcfce7"))
        painter.drawRoundedRect(QRectF(x - 58, y - 58, 116, 116), 8, 8)
        painter.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.Bold))
        painter.setPen(QColor("#15803d"))
        painter.drawText(QRectF(x - 34, y - 10, 68, 28), Qt.AlignmentFlag.AlignCenter, "出口")

    def _draw_tray_return_points(self, painter: QPainter) -> None:
        points = self.frame.get("tray_return_points", [])
        for pt in points:
            x, y = pt["x"], pt["y"]
            w, h = pt["width"], pt["height"]
            painter.setPen(QPen(QColor("#0369a1"), 2))
            painter.setBrush(QColor("#bae6fd"))
            painter.drawRoundedRect(QRectF(x - w/2, y - h/2, w, h), 4, 4)
            painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold))
            painter.setPen(QColor("#0284c7"))
            painter.drawText(QRectF(x - w/2, y - h/2, w, h), Qt.AlignmentFlag.AlignCenter, "收集处")

    def _draw_stalls(self, painter: QPainter) -> None:
        painter.setFont(QFont("Microsoft YaHei UI", 8))
        for stall in self.frame.get("stalls", []):
            x = stall["x"]
            y = stall["y"]
            self._draw_cook_timer(painter, stall)
            painter.setPen(QPen(QColor("#334155"), 1.5))
            painter.setBrush(QColor("#fff7ed"))
            painter.drawRoundedRect(QRectF(x - 38, y - 26, 76, 48), 6, 6)

            painter.setPen(QColor("#7c2d12"))
            painter.drawText(QRectF(x - 32, y - 22, 64, 16), Qt.AlignmentFlag.AlignCenter, f"W{stall['id'] + 1}")
            self._draw_chef_pig(painter, x, y + 2)

            painter.setPen(QColor("#475569"))
            painter.drawText(QRectF(x - 28, y + 4, 56, 18), Qt.AlignmentFlag.AlignCenter, f"排队 {stall['queue_count']}")

            painter.setPen(QPen(QColor("#cbd5e1"), 1))
            queue_x = x
            for index in range(min(stall["queue_count"], 9)):
                queue_y = y + 76 + index * 24
                painter.drawEllipse(QRectF(queue_x - 6, queue_y - 6, 12, 12))

    def _draw_cook_timer(self, painter: QPainter, stall: dict) -> None:
        x = stall["x"]
        y = stall["y"]
        progress = stall["cook_progress"]
        remaining = stall["cook_remaining"]
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
            x = table["x"]
            y = table["y"]
            painter.setPen(QPen(QColor("#475569"), 1.2))
            painter.setBrush(QColor("#fef3c7"))
            painter.drawRoundedRect(QRectF(x - 25, y - 17, 50, 34), 5, 5)

            seats = [(-34, -28), (26, -28), (-34, 20), (26, 20)]
            table_seats = table.get("seats", [])
            for index, (dx, dy) in enumerate(seats):
                seat = table_seats[index] if index < len(table_seats) else None
                status = "free"
                if isinstance(seat, dict):
                    status = seat.get("status", "free")
                elif seat is not None:
                    status = "occupied"
                
                if status == "occupied":
                    color = QColor("#fb7185")
                elif status == "reserved":
                    color = QColor("#fbbf24")
                else:
                    color = QColor("#e2e8f0")
                    
                painter.setBrush(color)
                painter.setPen(QPen(QColor("#64748b"), 1))
                painter.drawEllipse(QRectF(x + dx, y + dy, 16, 16))

    def _draw_students(self, painter: QPainter) -> None:
        for student in self.frame.get("students", []):
            self._draw_pig(painter, student)

    def _draw_pig(self, painter: QPainter, student: dict) -> None:
        x = student["x"]
        y = student["y"]
        state = student["state"]
        outline = QColor("#be185d")
        fill = QColor("#f9a8d4")
        if state == "queued":
            fill = QColor("#fbcfe8")
        elif state == "eating":
            fill = QColor("#fb7185")
        elif state in ("moving_to_table", "moving_to_seat"):
            fill = QColor("#fda4af")
        elif state == "leaving":
            fill = QColor("#fecdd3")
        elif state == "searching_seat":
            fill = QColor("#d8b4fe")
        elif state == "moving_to_tray_return":
            fill = QColor("#bae6fd")

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
        elif state == "searching_seat":
            painter.setPen(QColor("#2563eb"))
            painter.drawText(QRectF(x + 8, y - 24, 16, 16), Qt.AlignmentFlag.AlignCenter, "?座")
            painter.setPen(QPen(QColor("#831843"), 1.1))
            painter.drawLine(int(x - 4), int(y + 8), int(x + 4), int(y + 8))
        elif state in ("leaving", "done", "moving_to_tray_return"):
            painter.setPen(QPen(QColor("#831843"), 1.2))
            painter.drawArc(QRectF(x - 6, y + 2, 12, 9), 200 * 16, 140 * 16)
            if state in ("leaving", "done"):
                painter.setPen(QColor("#15803d"))
                painter.drawText(QRectF(x - 13, y + 11, 26, 14), Qt.AlignmentFlag.AlignCenter, "饱")
            else:
                painter.setPen(QColor("#0369a1"))
                painter.drawText(QRectF(x - 13, y + 11, 26, 14), Qt.AlignmentFlag.AlignCenter, "盘")
        elif state == "eating":
            painter.setPen(QPen(QColor("#831843"), 1.1))
            painter.drawArc(QRectF(x - 5, y + 4, 10, 7), 200 * 16, 140 * 16)
        else:
            painter.setPen(QPen(QColor("#831843"), 1.1))
            painter.drawArc(QRectF(x - 6, y + 6, 12, 8), 20 * 16, 140 * 16)

    def _draw_stats_panel(self, painter: QPainter) -> None:
        stats = self.frame.get("stats")
        if not stats:
            return
            
        width = self.frame.get("width", 1280)
        
        painter.setPen(QPen(QColor("#cbd5e1"), 1.5))
        painter.setBrush(QColor(255, 255, 255, 220))
        painter.drawRoundedRect(QRectF(width - 260, 20, 240, 160), 8, 8)
        
        painter.setPen(QColor("#0f172a"))
        painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold))
        painter.drawText(QRectF(width - 250, 25, 220, 20), Qt.AlignmentFlag.AlignLeft, "实时统计 (P0)")
        
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        y_offset = 55
        
        def format_time(seconds):
            if seconds is None:
                return "-"
            m = int(seconds // 60)
            s = int(seconds % 60)
            return f"{m}分{s}秒"
            
        def format_ratio(ratio):
            return f"{ratio*100:.1f}%" if ratio is not None else "-"
            
        lines = [
            f"平均等待: {format_time(stats.get('avg_wait_time'))}",
            f"平均就餐耗时: {format_time(stats.get('avg_total_time'))}",
            f"最高在场人数: {stats.get('max_active_students', '-')}",
            f"座位利用率: {format_ratio(stats.get('seat_utilization'))}",
        ]
        
        queue_stats = stats.get("stall_queue_stats", [])
        if queue_stats:
            max_q = max(q.get("max_queue_length", 0) for q in queue_stats)
            lines.append(f"单窗口最高排队: {max_q}")
        else:
            lines.append("单窗口最高排队: -")
            
        for line in lines:
            painter.drawText(QRectF(width - 250, y_offset, 220, 20), Qt.AlignmentFlag.AlignLeft, line)
            y_offset += 20
