from __future__ import annotations

from math import ceil, hypot
from typing import Any

from PyQt6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget

from utils.fonts import ui_font


class CanvasWidget(QWidget):
    zoomChanged = pyqtSignal(float)
    _STUDENT_MOVE_ANIMATION_MS = 90
    _STUDENT_TELEPORT_DISTANCE = 180.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(900, 620)
        self.frame: dict | None = None
        self.show_paths = False
        self.show_obstacles = False
        self.view_zoom = 1.0
        self._pan_offset = QPointF(0.0, 0.0)
        self._drag_start: QPointF | None = None
        self._hover_scene_pos: tuple[float, float] | None = None
        self._student_animations: dict[int, dict[str, float]] = {}
        self._student_animation_clock = QElapsedTimer()
        self._student_animation_timer = QTimer(self)
        self._student_animation_timer.setInterval(16)
        self._student_animation_timer.timeout.connect(self._advance_student_animation)
        self.setMouseTracking(True)

    def set_frame(self, frame: dict) -> None:
        adapted = self._frame_with_p1_fallback(frame)
        self._update_student_animations(adapted)
        self.frame = adapted
        self.update()

    def set_show_paths(self, show_paths: bool) -> None:
        self.show_paths = show_paths
        self.update()

    def set_show_obstacles(self, show_obstacles: bool) -> None:
        self.show_obstacles = show_obstacles
        self.update()

    def _frame_with_p1_fallback(self, frame: dict) -> dict:
        if not isinstance(frame, dict):
            return {}
        adapted = dict(frame)
        raw_stalls = frame.get("stalls")
        if isinstance(raw_stalls, list):
            adapted["stalls"] = [
                self._stall_with_p1_fallback(stall)
                for stall in raw_stalls
                if isinstance(stall, dict)
            ]
        else:
            adapted["stalls"] = []
        return adapted

    def _stall_with_p1_fallback(self, stall: dict) -> dict:
        adapted = dict(stall)
        dishes = self._p1_dishes_or_mock(adapted)
        adapted["dishes"] = dishes

        status = str(adapted.get("status") or "")
        if status not in {"pending", "open", "sold_out"}:
            status = "sold_out" if dishes and not any(self._dish_available(dish) for dish in dishes) else "open"
        adapted["status"] = status

        if "is_congested" not in adapted:
            adapted["is_congested"] = int(self._number(adapted.get("queue_count"), 0)) >= 8

        adapted["orders"] = self._p1_orders_or_mock(adapted, dishes)
        return adapted

    def _p1_dishes_or_mock(self, stall: dict) -> list[dict[str, Any]]:
        raw_dishes = stall.get("dishes")
        if isinstance(raw_dishes, list):
            dishes = [
                self._normalize_p1_dish(dish, stall, index)
                for index, dish in enumerate(raw_dishes)
                if isinstance(dish, dict)
            ]
            if dishes:
                return dishes
        return self._mock_stall_dishes(stall)

    def _normalize_p1_dish(self, dish: dict, stall: dict, index: int) -> dict[str, Any]:
        stall_id = int(self._number(stall.get("id"), 0))
        normalized = dict(dish)
        normalized.setdefault("id", stall_id * 100 + index + 1)
        normalized.setdefault("name", f"菜品{index + 1}")
        normalized.setdefault(
            "features",
            {
                "meat_ratio": self._number(stall.get("meat_ratio"), 0.5),
                "veg_ratio": self._number(stall.get("veg_ratio"), 0.5),
            },
        )
        normalized.setdefault("price", 10.0 + stall_id)
        normalized.setdefault("stock", 0)
        normalized.setdefault("cook_time", self._number(stall.get("cook_time"), 45.0))
        if "available" not in normalized:
            stock = self._number(normalized.get("stock"), None)
            normalized["available"] = True if stock is None else stock > 0
        return normalized

    def _p1_orders_or_mock(self, stall: dict, dishes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raw_orders = stall.get("orders")
        if isinstance(raw_orders, list):
            return [
                self._normalize_p1_order(order, stall, dishes, index)
                for index, order in enumerate(raw_orders)
                if isinstance(order, dict)
            ]
        return self._mock_stall_orders(stall, dishes)

    def _normalize_p1_order(
        self,
        order: dict,
        stall: dict,
        dishes: list[dict[str, Any]],
        index: int,
    ) -> dict[str, Any]:
        stall_id = int(self._number(stall.get("id"), 0))
        dish_id = dishes[index % len(dishes)].get("id") if dishes else None
        normalized = dict(order)
        normalized.setdefault("id", stall_id * 1000 + index + 1)
        normalized.setdefault("student_id", None)
        normalized.setdefault("stall_id", stall_id)
        normalized.setdefault("dish_id", dish_id)
        normalized.setdefault("created_at", None)
        normalized.setdefault("started_at", None)
        normalized.setdefault("finished_at", None)
        status = str(normalized.get("status") or "queued")
        normalized["status"] = status if status in {"queued", "cooking", "done", "cancelled"} else "queued"
        return normalized

    def _update_student_animations(self, next_frame: dict) -> None:
        next_students = [
            student
            for student in next_frame.get("students", [])
            if isinstance(student, dict) and student.get("id") is not None
        ]
        if not next_students:
            self._student_animations.clear()
            self._student_animation_timer.stop()
            self._student_animation_clock.invalidate()
            return

        previous_students = {}
        if isinstance(self.frame, dict):
            previous_students = {
                student.get("id"): student
                for student in self.frame.get("students", [])
                if isinstance(student, dict) and student.get("id") is not None
            }

        progress = self._student_animation_progress()
        animations: dict[int, dict[str, float]] = {}
        for student in next_students:
            student_id = int(student.get("id"))
            target_x = self._number(student.get("x"), 0.0)
            target_y = self._number(student.get("y"), 0.0)
            target_facing_x = max(-1.0, min(1.0, self._number(student.get("facing_x"), 1.0)))
            target_facing_y = max(-1.0, min(1.0, self._number(student.get("facing_y"), 0.0)))

            previous_student = previous_students.get(student.get("id"))
            if previous_student is None:
                start_x = target_x
                start_y = target_y
                start_facing_x = target_facing_x
                start_facing_y = target_facing_y
            else:
                start_x, start_y = self._interpolated_student_position(student_id, previous_student, progress)
                start_facing_x = self._interpolated_student_value(
                    student_id,
                    previous_student,
                    progress,
                    "facing_x",
                    1.0,
                )
                start_facing_y = self._interpolated_student_value(
                    student_id,
                    previous_student,
                    progress,
                    "facing_y",
                    0.0,
                )
                if hypot(target_x - start_x, target_y - start_y) > self._STUDENT_TELEPORT_DISTANCE:
                    start_x = target_x
                    start_y = target_y
                    start_facing_x = target_facing_x
                    start_facing_y = target_facing_y

            animations[student_id] = {
                "start_x": start_x,
                "start_y": start_y,
                "target_x": target_x,
                "target_y": target_y,
                "start_facing_x": start_facing_x,
                "start_facing_y": start_facing_y,
                "target_facing_x": target_facing_x,
                "target_facing_y": target_facing_y,
            }

        self._student_animations = animations
        self._student_animation_clock.restart()
        self._student_animation_timer.start()

    def _advance_student_animation(self) -> None:
        if self._student_animation_progress() >= 1.0:
            self._student_animation_timer.stop()
        self.update()

    def _student_animation_progress(self) -> float:
        if not self._student_animation_clock.isValid():
            return 1.0
        elapsed = self._student_animation_clock.elapsed()
        return max(0.0, min(1.0, elapsed / self._STUDENT_MOVE_ANIMATION_MS))

    def _interpolated_student_position(
        self,
        student_id: int,
        fallback_student: dict,
        progress: float | None = None,
    ) -> tuple[float, float]:
        animation = self._student_animations.get(student_id)
        if animation is None:
            return (
                self._number(fallback_student.get("x"), 0.0),
                self._number(fallback_student.get("y"), 0.0),
            )
        if progress is None:
            progress = self._student_animation_progress()
        eased = self._ease_out_cubic(progress)
        x = animation["start_x"] + (animation["target_x"] - animation["start_x"]) * eased
        y = animation["start_y"] + (animation["target_y"] - animation["start_y"]) * eased
        return x, y

    def _interpolated_student_value(
        self,
        student_id: int,
        fallback_student: dict,
        progress: float,
        key: str,
        default: float,
    ) -> float:
        animation = self._student_animations.get(student_id)
        if animation is None:
            return self._number(fallback_student.get(key), default)
        eased = self._ease_out_cubic(progress)
        start = animation.get(f"start_{key}", default)
        target = animation.get(f"target_{key}", default)
        return start + (target - start) * eased

    def _student_render_data(self, student: dict) -> dict:
        student_id = student.get("id")
        if student_id is None:
            return student
        render_student = dict(student)
        progress = self._student_animation_progress()
        x, y = self._interpolated_student_position(int(student_id), student, progress)
        render_student["x"] = x
        render_student["y"] = y
        render_student["facing_x"] = self._interpolated_student_value(
            int(student_id),
            student,
            progress,
            "facing_x",
            self._number(student.get("facing_x"), 1.0),
        )
        render_student["facing_y"] = self._interpolated_student_value(
            int(student_id),
            student,
            progress,
            "facing_y",
            self._number(student.get("facing_y"), 0.0),
        )
        return render_student

    def _ease_out_cubic(self, value: float) -> float:
        value = max(0.0, min(1.0, value))
        return 1.0 - (1.0 - value) ** 3

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
        painter.fillRect(self.rect(), QColor("#edf2f7"))

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
        self._scene_origin = QPointF(x_offset, y_offset)
        self._scene_scale = scale

        self._draw_floor(painter)
        if self.show_paths:
            self._draw_path_debug(painter)
        if self.show_obstacles:
            self._draw_obstacles_debug(painter)
        self._draw_door(painter)
        self._draw_exit(painter)
        self._draw_tray_return_points(painter)
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
            self._update_hover_scene_pos(current)
            self.update()
            event.accept()
            return
        self._update_hover_scene_pos(event.position())
        self.update()
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

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hover_scene_pos = None
        self.update()
        super().leaveEvent(event)

    def _update_hover_scene_pos(self, widget_pos: QPointF) -> None:
        origin = getattr(self, "_scene_origin", QPointF(0.0, 0.0))
        scale = getattr(self, "_scene_scale", 1.0)
        if scale <= 0:
            self._hover_scene_pos = None
            return
        self._hover_scene_pos = (
            (widget_pos.x() - origin.x()) / scale,
            (widget_pos.y() - origin.y()) / scale,
        )

    def _draw_empty_scene(self, painter: QPainter) -> None:
        painter.setPen(QColor("#475569"))
        painter.setFont(ui_font(14))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "点击开始仿真")

    def _draw_shadow(self, painter: QPainter, x: float, y: float, width: float, height: float, color: QColor) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QRectF(x - width / 2, y - height / 2, width, height))

    def _draw_iso_box(
        self,
        painter: QPainter,
        x: float,
        y: float,
        width: float,
        height: float,
        depth: float,
        top_color: QColor,
        side_color: QColor,
        edge_color: QColor,
    ) -> None:
        left = x - width / 2
        right = x + width / 2
        top = y - height / 2
        bottom = y + height / 2
        top_poly = QPolygonF([
            QPointF(left, top),
            QPointF(right, top),
            QPointF(right, bottom),
            QPointF(left, bottom),
        ])
        front_poly = QPolygonF([
            QPointF(left, bottom),
            QPointF(right, bottom),
            QPointF(right - depth * 0.55, bottom + depth),
            QPointF(left - depth * 0.55, bottom + depth),
        ])
        right_poly = QPolygonF([
            QPointF(right, top),
            QPointF(right, bottom),
            QPointF(right - depth * 0.55, bottom + depth),
            QPointF(right - depth * 0.55, top + depth),
        ])
        painter.setPen(QPen(edge_color.darker(115), 1.1))
        painter.setBrush(side_color.darker(108))
        painter.drawPolygon(front_poly)
        painter.setBrush(side_color)
        painter.drawPolygon(right_poly)
        painter.setBrush(top_color)
        painter.drawPolygon(top_poly)

    def _draw_floor(self, painter: QPainter) -> None:
        width, height = self._frame_size()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#e7efe2"))
        painter.drawRoundedRect(QRectF(18, 18, width - 36, height - 36), 18, 18)

        painter.setPen(QPen(QColor("#d2dfc9"), 1))
        for x in range(48, int(width) - 24, 56):
            painter.drawLine(x, 28, x - 92, int(height) - 34)
            painter.drawLine(x, 28, x + 92, int(height) - 34)
        painter.setPen(QPen(QColor("#c7d6bd"), 2))
        painter.drawRoundedRect(QRectF(18, 18, width - 36, height - 36), 18, 18)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#d6c8b8"))
        painter.drawRoundedRect(QRectF(34, 34, width - 68, 84), 12, 12)
        painter.setBrush(QColor("#d8e5ce"))
        painter.drawRoundedRect(QRectF(60, self._number(self.frame.get("height"), 800.0) - 96, width - 120, 48), 14, 14)
        painter.setPen(QPen(QColor("#a98f78"), 3))
        painter.drawLine(50, 118, int(width - 50), 118)
        painter.setPen(QColor("#6b4f3d"))
        painter.setFont(ui_font(10, QFont.Weight.Bold))
        painter.drawText(QRectF(70, 48, width - 140, 24), Qt.AlignmentFlag.AlignCenter, "靠墙出餐窗口区")

    def _draw_path_debug(self, painter: QPainter) -> None:
        painter.setFont(ui_font(8, QFont.Weight.Bold))
        colors = {
            "queue": QColor("#2563eb"),
            "top": QColor("#0891b2"),
            "bottom": QColor("#16a34a"),
            "aisle": QColor("#64748b"),
            "door": QColor("#1d4ed8"),
            "tray": QColor("#0f766e"),
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

        painter.setPen(QPen(QColor(220, 38, 38, 145), 1.6))
        painter.setBrush(QColor(248, 113, 113, 35))
        obstacle_frames = self.frame.get("obstacles") or self.frame.get("collision_boxes") or []
        for box in obstacle_frames:
            rect = self._obstacle_rect_frame(box)
            if rect is None:
                continue
            x, y, width, height, _ = rect
            painter.drawRoundedRect(QRectF(x - width / 2, y - height / 2, width, height), 5, 5)

        for student in self.frame.get("students", []):
            if not isinstance(student, dict):
                continue
            student_point = self._point((student.get("x"), student.get("y")))
            if student_point is None:
                continue
            stuck_time = self._number(student.get("stuck_time"), 0.0)
            if stuck_time > 1.2:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(239, 68, 68, 70))
                painter.drawEllipse(QRectF(student_point[0] - 22, student_point[1] - 16, 44, 32))
            points = [student_point, *(student.get("path") or [])]
            if len(points) < 2:
                continue
            painter.setPen(QPen(QColor("#db2777"), 2))
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
            target = self._point(points[-1])
            if target is not None:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#db2777"))
                painter.drawEllipse(QRectF(target[0] - 4, target[1] - 4, 8, 8))
                painter.setPen(QColor("#9d174d"))
                painter.setFont(ui_font(7, QFont.Weight.Bold))
                painter.drawText(QRectF(target[0] + 5, target[1] - 8, 34, 14), Qt.AlignmentFlag.AlignLeft, f"S{self._display_value(student.get('id'))}")

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
        entrances = self._entrance_frames()
        for entrance in entrances:
            rect = self._rect_frame(entrance, default_width=82.0, default_height=54.0)
            if rect is None:
                continue
            x, y, width, height, _ = rect
            weight = self._number(entrance.get("weight") if isinstance(entrance, dict) else None, 1.0)
            entrance_id = int(self._number(entrance.get("id") if isinstance(entrance, dict) else 0, 0))

            self._draw_shadow(painter, x, y + height * 0.42, width, 28, QColor(30, 64, 175, 45))
            self._draw_iso_box(painter, x, y, width, height, 18, QColor("#bfdbfe"), QColor("#60a5fa"), QColor("#1d4ed8"))
            painter.setFont(ui_font(10, QFont.Weight.Bold))
            painter.setPen(QColor("#1e3a8a"))
            label = "入口" if len(entrances) == 1 else f"入口 {entrance_id + 1}"
            painter.drawText(QRectF(x - width / 2, y - 12, width, 24), Qt.AlignmentFlag.AlignCenter, label)
            painter.setFont(ui_font(7, QFont.Weight.Bold))
            painter.drawText(QRectF(x - width / 2, y + height * 0.2, width, 16), Qt.AlignmentFlag.AlignCenter, f"权重 {weight:g}")

    def _entrance_frames(self) -> list[dict[str, Any]]:
        entrances = self.frame.get("entrances") if self.frame else None
        if isinstance(entrances, list):
            frames = [entrance for entrance in entrances if isinstance(entrance, dict)]
            if frames:
                return frames
        point = self._point(self.frame.get("door") if self.frame else None)
        if point is None:
            return []
        return [
            {
                "id": 0,
                "x": point[0],
                "y": point[1],
                "width": 82.0,
                "height": 54.0,
                "weight": 1.0,
            }
        ]

    def _exit_frames(self) -> list[dict[str, Any]]:
        exits = self.frame.get("exits") if self.frame else None
        if isinstance(exits, list):
            frames = [exit_frame for exit_frame in exits if isinstance(exit_frame, dict)]
            if frames:
                return frames
        point = self._point(self.frame.get("exit") if self.frame else None)
        if point is None:
            return []
        return [
            {
                "id": 0,
                "x": point[0],
                "y": point[1],
                "width": 116.0,
                "height": 70.0,
                "is_congested": False,
            }
        ]

    def _draw_obstacles_debug(self, painter: QPainter) -> None:
        obstacle_rects = self._obstacle_rects()
        if not obstacle_rects:
            return
        for left, top, right, bottom, kind in obstacle_rects:
            color = self._obstacle_color(kind)
            rect = QRectF(left, top, max(1.0, right - left), max(1.0, bottom - top))
            painter.setPen(QPen(color.darker(130), 1.6))
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 42))
            painter.drawRoundedRect(rect, 5, 5)
            if kind:
                painter.setPen(color.darker(150))
                painter.setFont(ui_font(7, QFont.Weight.Bold))
                painter.drawText(rect.adjusted(4, 2, -4, -2), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, kind)

    def _obstacle_rects(self) -> list[tuple[float, float, float, float, str]]:
        obstacles = self.frame.get("obstacles") if self.frame else None
        rects: list[tuple[float, float, float, float, str]] = []
        if isinstance(obstacles, list):
            for obstacle in obstacles:
                if not isinstance(obstacle, dict):
                    continue
                left = self._number(obstacle.get("left"), None)
                top = self._number(obstacle.get("top"), None)
                right = self._number(obstacle.get("right"), None)
                bottom = self._number(obstacle.get("bottom"), None)
                if None in (left, top, right, bottom):
                    continue
                rects.append((left, top, right, bottom, str(obstacle.get("kind") or "obstacle")))
            if rects:
                return rects

        for box in self.frame.get("collision_boxes", []) if self.frame else []:
            rect = self._rect_frame(box, default_width=1.0, default_height=1.0)
            if rect is None:
                continue
            x, y, width, height, _ = rect
            rects.append((x - width / 2, y - height / 2, x + width / 2, y + height / 2, "collision"))
        return rects

    def _obstacle_color(self, kind: str) -> QColor:
        colors = {
            "wall": QColor("#64748b"),
            "table": QColor("#d97706"),
            "stall": QColor("#dc2626"),
            "window": QColor("#dc2626"),
            "collision": QColor("#ef4444"),
        }
        return colors.get(kind, QColor("#ef4444"))

    def _draw_exit(self, painter: QPainter) -> None:
        exits = self._exit_frames()
        for exit_frame in exits:
            rect = self._rect_frame(exit_frame, default_width=116.0, default_height=70.0)
            if rect is None:
                continue
            x, y, width, height, congested = rect
            exit_id = int(self._number(exit_frame.get("id") if isinstance(exit_frame, dict) else 0, 0))
            edge = QColor("#b45309" if congested else "#15803d")
            top = QColor("#fed7aa" if congested else "#bbf7d0")
            side = QColor("#fb923c" if congested else "#86efac")

            self._draw_shadow(painter, x, y + height * 0.37, width, 36, QColor(22, 101, 52, 45))
            self._draw_iso_box(painter, x, y, width, height, 20, top, side, edge)
            painter.setFont(ui_font(10, QFont.Weight.Bold))
            painter.setPen(edge.darker(115))
            label = "出口" if len(exits) == 1 else f"出口 {exit_id + 1}"
            painter.drawText(QRectF(x - width / 2, y - 12, width, 24), Qt.AlignmentFlag.AlignCenter, label)
            if congested:
                painter.setFont(ui_font(7, QFont.Weight.Bold))
                painter.drawText(QRectF(x - width / 2, y + height * 0.2, width, 16), Qt.AlignmentFlag.AlignCenter, "拥堵")

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
            self._draw_shadow(painter, x, y + 34, 96, 24, QColor(120, 53, 15, 45))
            self._draw_iso_box(painter, x, y + 2, 88, 46, 16, QColor("#fed7aa"), QColor("#fb923c"), QColor("#9a3412"))

            stall_id = int(self._number(stall.get("id"), 0))
            painter.setPen(QColor("#7c2d12"))
            painter.setFont(ui_font(8, QFont.Weight.Bold))
            painter.drawText(QRectF(x - 34, y - 23, 68, 16), Qt.AlignmentFlag.AlignCenter, f"窗口 {stall_id + 1}")
            self._draw_chef_pig(painter, x, y + 3)

            queue_count = int(self._number(stall.get("queue_count"), 0))
            painter.setPen(QColor("#7c2d12"))
            painter.drawText(QRectF(x - 30, y + 11, 60, 18), Qt.AlignmentFlag.AlignCenter, f"{queue_count} 人")
            self._draw_stall_dishes(painter, stall, x, y)
            self._draw_stall_status(painter, stall, x, y)

            painter.setPen(QPen(QColor(148, 163, 184, 120), 1))
            painter.setBrush(QColor(255, 247, 237, 95))
            painter.drawRoundedRect(QRectF(x - 16, y + 58, 32, 222), 10, 10)
            painter.setPen(QPen(QColor("#cbd5e1"), 1))
            painter.setBrush(QColor("#fbbf24"))
            queue_x = x
            for index in range(min(queue_count, 9)):
                queue_y = y + 76 + index * 24
                self._draw_shadow(painter, queue_x, queue_y + 5, 18, 7, QColor(51, 65, 85, 42))
                painter.drawEllipse(QRectF(queue_x - 6, queue_y - 6, 12, 12))
            self._draw_stall_orders(painter, stall, x, y)

    def _draw_stall_dishes(self, painter: QPainter, stall: dict, x: float, y: float) -> None:
        dishes = self._stall_dishes(stall)
        if not dishes:
            return

        panel_width = 104.0
        row_height = 16.0
        visible_dishes = dishes[:2]
        panel_height = 18.0 + len(visible_dishes) * row_height
        left = x - panel_width / 2
        top = y - 82.0

        painter.setPen(QPen(QColor(234, 179, 8, 135), 1))
        painter.setBrush(QColor(255, 251, 235, 232))
        painter.drawRoundedRect(QRectF(left, top, panel_width, panel_height), 6, 6)

        painter.setPen(QColor("#854d0e"))
        painter.setFont(ui_font(7, QFont.Weight.Bold))
        suffix = f" +{len(dishes) - len(visible_dishes)}" if len(dishes) > len(visible_dishes) else ""
        painter.drawText(QRectF(left + 6, top + 3, panel_width - 12, 12), Qt.AlignmentFlag.AlignLeft, f"菜品{suffix}")

        painter.setFont(ui_font(7))
        for index, dish in enumerate(visible_dishes):
            row_top = top + 18.0 + index * row_height
            available = self._dish_available(dish)
            name = str(dish.get("name") or f"菜品{index + 1}")
            name = painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, 38)
            price = self._format_price(dish.get("price"))
            stock = self._display_value(dish.get("stock"))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#dcfce7" if available else "#fee2e2"))
            painter.drawRoundedRect(QRectF(left + 6, row_top + 2, 24, 12), 5, 5)

            painter.setPen(QColor("#166534" if available else "#991b1b"))
            painter.setFont(ui_font(7, QFont.Weight.Bold))
            painter.drawText(QRectF(left + 7, row_top + 1, 22, 13), Qt.AlignmentFlag.AlignCenter, "售" if available else "罄")

            painter.setPen(QColor("#334155"))
            painter.setFont(ui_font(7))
            painter.drawText(QRectF(left + 33, row_top + 1, 40, 14), Qt.AlignmentFlag.AlignLeft, name)
            painter.drawText(QRectF(left + 71, row_top + 1, 20, 14), Qt.AlignmentFlag.AlignRight, price)
            painter.drawText(QRectF(left + 93, row_top + 1, 8, 14), Qt.AlignmentFlag.AlignRight, stock)

    def _stall_dishes(self, stall: dict) -> list[dict[str, Any]]:
        raw_dishes = stall.get("dishes")
        if isinstance(raw_dishes, list):
            return [dish for dish in raw_dishes if isinstance(dish, dict)]
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

    def _draw_stall_status(self, painter: QPainter, stall: dict, x: float, y: float) -> None:
        status = self._stall_status(stall)
        label, text_color, fill_color = {
            "pending": ("待营业", QColor("#92400e"), QColor("#fef3c7")),
            "open": ("营业中", QColor("#166534"), QColor("#dcfce7")),
            "sold_out": ("已售罄", QColor("#991b1b"), QColor("#fee2e2")),
        }.get(status, ("营业中", QColor("#166534"), QColor("#dcfce7")))

        rect = QRectF(x - 28, y + 31, 56, 15)
        painter.setPen(QPen(text_color.lighter(125), 1))
        painter.setBrush(fill_color)
        painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(text_color)
        painter.setFont(ui_font(7, QFont.Weight.Bold))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

    def _draw_stall_orders(self, painter: QPainter, stall: dict, x: float, y: float) -> None:
        orders = self._stall_orders(stall)
        if not orders:
            return

        visible_orders = orders[:2]
        panel_width = 78.0
        row_height = 16.0
        panel_height = 18.0 + len(visible_orders) * row_height
        left = x + 22.0
        top = y + 58.0

        painter.setPen(QPen(QColor(148, 163, 184, 135), 1))
        painter.setBrush(QColor(248, 250, 252, 232))
        painter.drawRoundedRect(QRectF(left, top, panel_width, panel_height), 6, 6)

        suffix = f" +{len(orders) - len(visible_orders)}" if len(orders) > len(visible_orders) else ""
        painter.setPen(QColor("#334155"))
        painter.setFont(ui_font(7, QFont.Weight.Bold))
        painter.drawText(QRectF(left + 6, top + 3, panel_width - 12, 12), Qt.AlignmentFlag.AlignLeft, f"订单{suffix}")

        for index, order in enumerate(visible_orders):
            row_top = top + 18.0 + index * row_height
            status = str(order.get("status") or "queued")
            status_label, status_color = self._order_status_display(status)
            order_id = self._display_value(order.get("id"))
            row_rect = QRectF(left + 5, row_top + 1, panel_width - 10, 14)
            hovered = self._is_hovered(row_rect)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(status_color.lighter(180))
            painter.drawRoundedRect(QRectF(left + 5, row_top + 2, 18, 12), 5, 5)
            painter.setPen(status_color.darker(130))
            painter.setFont(ui_font(7, QFont.Weight.Bold))
            painter.drawText(QRectF(left + 6, row_top + 1, 16, 13), Qt.AlignmentFlag.AlignCenter, status_label)

            painter.setPen(QColor("#334155"))
            painter.setFont(ui_font(7))
            painter.drawText(QRectF(left + 26, row_top + 1, 46, 14), Qt.AlignmentFlag.AlignLeft, f"#{order_id}")
            if hovered:
                self._draw_order_tooltip(painter, order, status, status_color, left + panel_width + 4, row_top - 6)

    def _stall_status(self, stall: dict) -> str:
        status = stall.get("status")
        if status:
            return str(status)
        dishes = self._stall_dishes(stall)
        return "sold_out" if dishes and not any(self._dish_available(dish) for dish in dishes) else "open"

    def _stall_orders(self, stall: dict) -> list[dict[str, Any]]:
        raw_orders = stall.get("orders")
        if isinstance(raw_orders, list):
            return [order for order in raw_orders if isinstance(order, dict)]
        return self._mock_stall_orders(stall)

    def _mock_stall_orders(
        self,
        stall: dict,
        dishes: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        queue_count = int(self._number(stall.get("queue_count"), 0))
        if queue_count <= 0:
            return []
        stall_id = int(self._number(stall.get("id"), 0))
        dishes = dishes if dishes is not None else self._stall_dishes(stall)
        dish_id = dishes[0].get("id") if dishes else None
        status_cycle = ["queued", "cooking", "done"]
        return [
            {
                "id": stall_id * 1000 + index + 1,
                "student_id": stall_id * 100 + index + 1,
                "stall_id": stall_id,
                "dish_id": dish_id,
                "created_at": None,
                "started_at": None,
                "finished_at": None,
                "status": status_cycle[min(index, len(status_cycle) - 1)],
            }
            for index in range(min(queue_count, 3))
        ]

    def _order_status_display(self, status: str) -> tuple[str, QColor]:
        displays = {
            "queued": ("排", QColor("#2563eb")),
            "cooking": ("做", QColor("#ea580c")),
            "done": ("完", QColor("#16a34a")),
            "cancelled": ("取", QColor("#64748b")),
        }
        return displays.get(status, ("排", QColor("#2563eb")))

    def _draw_order_tooltip(
        self,
        painter: QPainter,
        order: dict,
        status: str,
        status_color: QColor,
        left: float,
        top: float,
    ) -> None:
        width = 126.0
        height = 72.0
        frame_width, frame_height = self._frame_size()
        left = min(left, frame_width - width - 12)
        top = min(max(24.0, top), frame_height - height - 24)
        rect = QRectF(left, top, width, height)

        painter.setPen(QPen(QColor(71, 85, 105, 160), 1))
        painter.setBrush(QColor(255, 255, 255, 242))
        painter.drawRoundedRect(rect, 7, 7)

        status_name = self._order_status_name(status)
        painter.setPen(status_color.darker(125))
        painter.setFont(ui_font(8, QFont.Weight.Bold))
        painter.drawText(QRectF(left + 8, top + 6, width - 16, 14), Qt.AlignmentFlag.AlignLeft, f"订单 {self._display_value(order.get('id'))}")
        painter.drawText(QRectF(left + 8, top + 22, width - 16, 14), Qt.AlignmentFlag.AlignLeft, f"状态：{status_name}")

        painter.setPen(QColor("#334155"))
        painter.setFont(ui_font(7))
        lines = [
            f"学生：{self._display_value(order.get('student_id'))}",
            f"菜品：{self._display_value(order.get('dish_id'))}",
            f"窗口：{self._display_value(order.get('stall_id'))}",
        ]
        for index, line in enumerate(lines):
            painter.drawText(QRectF(left + 8, top + 38 + index * 11, width - 16, 11), Qt.AlignmentFlag.AlignLeft, line)

    def _is_hovered(self, rect: QRectF) -> bool:
        if self._hover_scene_pos is None:
            return False
        x, y = self._hover_scene_pos
        return rect.contains(QPointF(x, y))

    def _order_status_name(self, status: str) -> str:
        names = {
            "queued": "排队等待",
            "cooking": "出餐中",
            "done": "已完成",
            "cancelled": "已取消",
        }
        return names.get(status, status or "-")

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
            table_type, seat_count = self._table_type_and_seat_count(table)
            table_width = {2: 52.0, 4: 64.0, 6: 84.0}.get(seat_count, 64.0)
            table_height = 38.0

            self._draw_shadow(painter, x, y + 28, table_width + 22, 24, QColor(71, 85, 105, 40))
            self._draw_iso_box(painter, x, y, table_width, table_height, 14, QColor("#fde68a"), QColor("#d97706"), QColor("#92400e"))
            painter.setPen(QPen(QColor("#92400e"), 1.2))
            painter.drawLine(int(x - table_width * 0.33), int(y + 18), int(x - table_width * 0.39), int(y + 34))
            painter.drawLine(int(x + table_width * 0.33), int(y + 18), int(x + table_width * 0.27), int(y + 34))

            painter.setPen(QColor("#92400e"))
            painter.setFont(ui_font(7, QFont.Weight.Bold))
            painter.drawText(QRectF(x - table_width / 2, y - 8, table_width, 14), Qt.AlignmentFlag.AlignCenter, f"{seat_count}人")

            seats = table.get("seat_frames") or table.get("seats") or []
            seat_offsets = self._table_seat_offsets(int(table.get("seat_count") or len(seats) or 4))
            for index, (dx, dy) in enumerate(seat_offsets):
                seat = seats[index] if index < len(seats) else None
                status = self._seat_status(seat)
                color = self._seat_color(status)
                self._draw_shadow(painter, x + dx + 8, y + dy + 13, 22, 9, QColor(51, 65, 85, 38))
                painter.setBrush(color)
                painter.setPen(QPen(color.darker(130), 1))
                painter.drawRoundedRect(QRectF(x + dx, y + dy, 18, 18), 6, 6)
                painter.setBrush(color.lighter(112))
                painter.drawEllipse(QRectF(x + dx + 3, y + dy - 4, 12, 10))
                self._draw_seat_status_marker(painter, x + dx, y + dy, status, seat)

    def _table_type_and_seat_count(self, table: dict) -> tuple[str, int]:
        table_type = str(table.get("table_type") or "").lower()
        type_to_count = {"two": 2, "four": 4, "six": 6}
        seat_count = int(self._number(table.get("seat_count"), type_to_count.get(table_type, 4)))
        if seat_count not in (2, 4, 6):
            seat_count = type_to_count.get(table_type, 4)
        if table_type not in type_to_count:
            table_type = {2: "two", 4: "four", 6: "six"}.get(seat_count, "four")
        return table_type, seat_count

    def _seat_offsets_for_table(self, seat_count: int, table_width: float) -> list[tuple[float, float]]:
        side_x = table_width / 2 + 14
        if seat_count == 2:
            return [(-side_x - 4, -8), (side_x - 14, -8)]
        if seat_count == 6:
            return [
                (-side_x - 4, -32),
                (side_x - 14, -32),
                (-side_x - 4, -4),
                (side_x - 14, -4),
                (-side_x - 4, 24),
                (side_x - 14, 24),
            ]
        return [(-side_x - 4, -32), (side_x - 14, -32), (-side_x - 4, 24), (side_x - 14, 24)]

    def _draw_seat_status_marker(self, painter: QPainter, x: float, y: float, status: str, seat: Any) -> None:
        if status == "free":
            return
        label = "预" if status == "reserved" else "占"
        color = QColor("#92400e") if status == "reserved" else QColor("#9f1239")

        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.setBrush(color)
        painter.drawEllipse(QRectF(x + 9, y - 8, 12, 12))
        painter.setPen(QColor("#ffffff"))
        painter.setFont(ui_font(6, QFont.Weight.Bold))
        painter.drawText(QRectF(x + 9, y - 8, 12, 12), Qt.AlignmentFlag.AlignCenter, label)

        student_id = self._seat_student_id(seat)
        if student_id is not None:
            painter.setPen(color.darker(125))
            painter.setFont(ui_font(6, QFont.Weight.Bold))
            painter.drawText(QRectF(x - 4, y + 17, 30, 10), Qt.AlignmentFlag.AlignCenter, f"S{student_id}")

    def _table_seat_offsets(self, seat_count: int) -> list[tuple[int, int]]:
        if seat_count <= 2:
            return [(-47, -4), (31, -4)]
        if seat_count <= 4:
            return [(-47, -32), (31, -32), (-47, 24), (31, 24)]
        return [(-51, -40), (35, -40), (-51, -4), (35, -4), (-51, 32), (35, 32)][:seat_count]

    def _draw_students(self, painter: QPainter) -> None:
        students = [
            self._student_render_data(student)
            for student in self.frame.get("students", [])
            if isinstance(student, dict)
        ]
        students.sort(key=lambda item: self._number(item.get("y"), 0.0))
        for student in students:
            self._draw_pig(painter, student)

    def _draw_pig(self, painter: QPainter, student: dict) -> None:
        point = self._point((student.get("x"), student.get("y")))
        if point is None:
            return
        x, y = point
        state = str(student.get("state") or "unknown")
        fill = self._student_fill_color(state)
        facing_x = max(-1.0, min(1.0, self._number(student.get("facing_x"), 1.0)))
        lean = 4.0 if facing_x >= 0 else -4.0

        self._draw_shadow(painter, x, y + 14, 30, 11, QColor(51, 65, 85, 55))
        painter.setPen(QPen(fill.darker(145), 1.1))
        painter.setBrush(fill.darker(108))
        painter.drawRoundedRect(QRectF(x - 8, y + 2, 18, 18), 7, 7)
        painter.setPen(QPen(QColor("#475569"), 1.0))
        painter.drawLine(int(x - 3), int(y + 18), int(x - 8), int(y + 25))
        painter.drawLine(int(x + 7), int(y + 18), int(x + 13), int(y + 24))

        head_x = x + lean
        head_y = y - 8
        painter.setPen(QPen(QColor("#be185d"), 1.4))
        painter.setBrush(fill)
        painter.drawEllipse(QRectF(head_x - 14, head_y - 12, 28, 25))
        painter.setBrush(fill.lighter(112))
        painter.drawEllipse(QRectF(head_x - 16, head_y - 15, 9, 9))
        painter.drawEllipse(QRectF(head_x + 7, head_y - 15, 9, 9))
        painter.setBrush(QColor("#fecdd3"))
        painter.drawEllipse(QRectF(head_x - 8, head_y - 1, 16, 10))
        painter.setBrush(QColor(255, 255, 255, 120))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(head_x - 8, head_y - 9, 8, 5))
        painter.setBrush(QColor("#9f1239"))
        painter.drawEllipse(QRectF(head_x - 4, head_y + 2, 2.5, 2.5))
        painter.drawEllipse(QRectF(head_x + 2, head_y + 2, 2.5, 2.5))

        painter.setPen(QPen(QColor("#831843"), 1.2))
        eye_offset = 2.0 if facing_x >= 0 else -2.0
        painter.drawPoint(int(head_x - 5 + eye_offset), int(head_y - 4))
        painter.drawPoint(int(head_x + 5 + eye_offset), int(head_y - 4))
        self._draw_student_expression(painter, head_x, head_y, state)
        self._draw_group_badge(painter, student, head_x, head_y)

    def _draw_group_badge(self, painter: QPainter, student: dict, x: float, y: float) -> None:
        group_id = student.get("group_id")
        if group_id is None:
            return
        group_text = self._display_value(group_id)
        group_size = self._number(student.get("group_size"), None)
        color = self._group_color(group_id)
        badge_x = x - 22
        badge_y = y - 30

        painter.setPen(QPen(color.darker(135), 1))
        painter.setBrush(color.lighter(155))
        painter.drawEllipse(QRectF(badge_x, badge_y, 12, 12))

        painter.setPen(color.darker(150))
        painter.setFont(ui_font(6, QFont.Weight.Bold))
        painter.drawText(QRectF(badge_x + 13, badge_y - 1, 34, 14), Qt.AlignmentFlag.AlignLeft, f"G{group_text}")
        if group_size is not None and group_size > 1:
            painter.drawText(QRectF(badge_x + 13, badge_y + 9, 24, 12), Qt.AlignmentFlag.AlignLeft, f"x{int(group_size)}")

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
            edge = QColor("#0f766e" if not congested else "#b45309")
            top = QColor("#99f6e4" if not congested else "#fed7aa")
            side = QColor("#14b8a6" if not congested else "#fb923c")
            self._draw_shadow(painter, x, y + height * 0.34, width * 0.9, 30, QColor(15, 118, 110, 48))
            self._draw_iso_box(painter, x, y, width, height * 0.58, 24, top, side, edge)
            painter.setPen(QPen(edge.darker(125), 2))
            painter.setBrush(QColor("#0f172a"))
            painter.drawRoundedRect(QRectF(x - width * 0.22, y - 3, width * 0.44, 12), 5, 5)
            painter.setFont(ui_font(9, QFont.Weight.Bold))
            painter.setPen(QColor("#115e59" if not congested else "#9a3412"))
            painter.drawText(QRectF(x - width / 2, y - height * 0.42, width, 20), Qt.AlignmentFlag.AlignCenter, "碗筷回收")
            painter.setPen(QPen(QColor("#475569"), 1.2))
            for index in range(3):
                painter.drawRoundedRect(QRectF(x + width * 0.25, y - 4 + index * 7, 24, 6), 3, 3)

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

    def _obstacle_rect_frame(self, value: Any) -> tuple[float, float, float, float, bool] | None:
        if isinstance(value, dict) and all(key in value for key in ("left", "top", "right", "bottom")):
            left = self._number(value.get("left"), 0.0)
            top = self._number(value.get("top"), 0.0)
            right = self._number(value.get("right"), left)
            bottom = self._number(value.get("bottom"), top)
            width = max(1.0, right - left)
            height = max(1.0, bottom - top)
            return left + width / 2.0, top + height / 2.0, width, height, False
        return self._rect_frame(value, default_width=1.0, default_height=1.0)

    def _seat_status(self, seat: Any) -> str:
        if isinstance(seat, dict):
            status = seat.get("status")
            if status:
                return str(status)
            return "occupied" if seat.get("student_id") is not None else "free"
        return "occupied" if seat is not None else "free"

    def _seat_student_id(self, seat: Any) -> Any:
        if isinstance(seat, dict):
            return seat.get("student_id")
        return seat

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

    def _group_color(self, group_id: Any) -> QColor:
        palette = [
            QColor("#38bdf8"),
            QColor("#a78bfa"),
            QColor("#34d399"),
            QColor("#fbbf24"),
            QColor("#fb7185"),
            QColor("#2dd4bf"),
            QColor("#f97316"),
            QColor("#818cf8"),
        ]
        try:
            index = int(group_id)
        except (TypeError, ValueError):
            index = sum(ord(char) for char in str(group_id))
        return palette[index % len(palette)]

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
