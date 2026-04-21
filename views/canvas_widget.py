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

    def set_frame(self, frame: dict) -> None:
        self.frame = frame
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f7f8f3"))

        if not self.frame:
            self._draw_empty_scene(painter)
            return

        scale = min(self.width() / self.frame["width"], self.height() / self.frame["height"])
        x_offset = (self.width() - self.frame["width"] * scale) / 2
        y_offset = (self.height() - self.frame["height"] * scale) / 2
        painter.translate(x_offset, y_offset)
        painter.scale(scale, scale)
        self._draw_floor(painter)
        self._draw_door(painter)
        self._draw_exit(painter)
        self._draw_stalls(painter)
        self._draw_tables(painter)
        self._draw_students(painter)
        self._draw_header(painter)

    def _draw_empty_scene(self, painter: QPainter) -> None:
        painter.setPen(QColor("#475569"))
        painter.setFont(QFont("Microsoft YaHei UI", 14))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "点击开始仿真")

    def _draw_floor(self, painter: QPainter) -> None:
        width = self.frame["width"]
        height = self.frame["height"]
        painter.setPen(QPen(QColor("#d7dccd"), 1))
        for x in range(0, int(width) + 1, 56):
            painter.drawLine(x, 0, x, int(height))
        for y in range(0, int(height) + 1, 56):
            painter.drawLine(0, y, int(width), y)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#e9efe0"))
        painter.drawRoundedRect(QRectF(18, 18, width - 36, height - 36), 8, 8)

    def _draw_header(self, painter: QPainter) -> None:
        game_time = self.frame["game_time"]
        duration = self.frame["duration"]
        minutes = int(game_time // 60)
        seconds = int(game_time % 60)
        total_minutes = int(duration // 60)

        painter.setPen(QColor("#0f172a"))
        painter.setFont(QFont("Microsoft YaHei UI", 12, QFont.Weight.Bold))
        text = (
            f"仿真 {minutes:02d}:{seconds:02d} / {total_minutes:02d}:00    "
            f"场内 {self.frame['active_students']}    "
            f"已生成 {self.frame['spawned_students']}    "
            f"已离场 {self.frame['served_students']}"
        )
        painter.drawText(QRectF(28, self.frame["height"] - 38, 760, 30), Qt.AlignmentFlag.AlignLeft, text)

    def _draw_door(self, painter: QPainter) -> None:
        x, y = self.frame["door"]
        painter.setPen(QPen(QColor("#1f2937"), 2))
        painter.setBrush(QColor("#dbeafe"))
        painter.drawRoundedRect(QRectF(x - 36, y - 36, 72, 72), 6, 6)
        painter.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.Bold))
        painter.setPen(QColor("#1d4ed8"))
        painter.drawText(QRectF(x - 34, y - 10, 68, 28), Qt.AlignmentFlag.AlignCenter, "大门")

    def _draw_exit(self, painter: QPainter) -> None:
        x, y = self.frame["exit"]
        painter.setPen(QPen(QColor("#166534"), 2))
        painter.setBrush(QColor("#dcfce7"))
        painter.drawRoundedRect(QRectF(x - 36, y - 36, 72, 72), 6, 6)
        painter.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.Bold))
        painter.setPen(QColor("#15803d"))
        painter.drawText(QRectF(x - 34, y - 10, 68, 28), Qt.AlignmentFlag.AlignCenter, "出口")

    def _draw_stalls(self, painter: QPainter) -> None:
        painter.setFont(QFont("Microsoft YaHei UI", 8))
        for stall in self.frame["stalls"]:
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
        for table in self.frame["tables"]:
            x = table["x"]
            y = table["y"]
            painter.setPen(QPen(QColor("#475569"), 1.2))
            painter.setBrush(QColor("#fef3c7"))
            painter.drawRoundedRect(QRectF(x - 25, y - 17, 50, 34), 5, 5)

            seats = [(-34, -28), (26, -28), (-34, 20), (26, 20)]
            for index, (dx, dy) in enumerate(seats):
                occupied = table["seats"][index] is not None
                painter.setBrush(QColor("#fb7185") if occupied else QColor("#e2e8f0"))
                painter.setPen(QPen(QColor("#64748b"), 1))
                painter.drawEllipse(QRectF(x + dx, y + dy, 16, 16))

    def _draw_students(self, painter: QPainter) -> None:
        for student in self.frame["students"]:
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
