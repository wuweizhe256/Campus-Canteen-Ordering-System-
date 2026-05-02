from __future__ import annotations

import random
import time
from typing import Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from models.entities import RunSummary, SeatStatus, SimulationConfig, Stall, Student, StudentState, Table
from utils.helpers import clamp, distance, manhattan_2d, move_towards


class SimulationWorker(QObject):
    frameReady = pyqtSignal(object)
    statusChanged = pyqtSignal(str)
    finished = pyqtSignal(object)
    errorOccurred = pyqtSignal(object)

    def __init__(self, config: SimulationConfig) -> None:
        super().__init__()
        self.config = config
        self.time_scale = config.time_scale
        self.rng = random.Random(config.seed)
        self.width = 1280
        self.height = 800
        self.table_columns = 6
        self.queue_walkway_y = 142.0
        self.top_walkway_y = 250.0
        self.bottom_walkway_y = 742.0
        self.door = (52.0, 72.0)
        self.exit = (1228.0, 740.0)
        self.tray_return_points: list[tuple[float, float, float, float]] = []
        self.stalls: list[Stall] = []
        self.tables: list[Table] = []
        self.students: dict[int, Student] = {}
        self.game_time = 0.0
        self.next_student_id = 1
        self.spawned_students = 0
        self.served_students = 0
        self.max_active_students_seen = 0
        self._stop_requested = False
        self._paused = False

    @pyqtSlot()
    def run(self) -> None:
        try:
            self._initialize()
            self.statusChanged.emit("运行中")
            last_real_time = time.perf_counter()

            while not self._stop_requested and self.game_time < self.config.duration_game_seconds:
                now = time.perf_counter()
                if self._paused:
                    last_real_time = now
                    QThread.msleep(40)
                    continue

                real_delta = now - last_real_time
                last_real_time = now
                game_delta = real_delta * self.time_scale

                self.game_time += game_delta
                self._spawn_due_students()
                self._complete_ready_food()
                self._update_students(game_delta)
                self._separate_students(game_delta)
                self.max_active_students_seen = max(
                    self.max_active_students_seen,
                    self._active_student_count(),
                )
                self.frameReady.emit(self._build_frame())
                QThread.msleep(16)

            status = "已停止" if self._stop_requested else "已结束"
            self.statusChanged.emit(status)
            self.frameReady.emit(self._build_frame())
            self.finished.emit(
                RunSummary(
                    status=status,
                    game_time=min(self.game_time, self.config.duration_game_seconds),
                    spawned_students=self.spawned_students,
                    served_students=self.served_students,
                    active_students=self._active_student_count(),
                )
            )
        except Exception as exc:  # pragma: no cover - delivered to UI at runtime
            self.errorOccurred.emit(exc)

    @pyqtSlot()
    def stop(self) -> None:
        self._stop_requested = True

    @pyqtSlot(bool)
    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self.statusChanged.emit("已暂停" if paused else "运行中")

    @pyqtSlot(float)
    def set_time_scale(self, time_scale: float) -> None:
        self.time_scale = max(1.0, min(24.0, time_scale))

    def _initialize(self) -> None:
        self._build_stalls()
        self._build_tables()
        self._build_tray_return_points()
        self.students.clear()
        self.game_time = 0.0
        self.next_student_id = 1
        self.spawned_students = 0
        self.served_students = 0
        self.max_active_students_seen = 0

    def _build_stalls(self) -> None:
        self.stalls.clear()
        count = max(1, self.config.stall_count)
        left = 135.0
        right = self.width - 45.0
        gap = 0.0 if count == 1 else (right - left) / (count - 1)
        for index in range(count):
            self.stalls.append(
                Stall(
                    id=index,
                    x=left + gap * index,
                    y=76.0,
                    meat_ratio=self.rng.uniform(0.0, 1.0),
                    veg_ratio=self.rng.uniform(0.0, 1.0),
                    cook_time=self.rng.uniform(12.0, 28.0),
                )
            )

    def _build_tables(self) -> None:
        self.tables.clear()
        count = max(1, self.config.table_count)
        start_x = 185.0
        start_y = 350.0
        gap_x = 175.0
        gap_y = 115.0
        for index in range(count):
            row = index // self.table_columns
            column = index % self.table_columns
            self.tables.append(
                Table(
                    id=index,
                    x=start_x + column * gap_x,
                    y=start_y + row * gap_y,
                )
            )

    def _build_tray_return_points(self) -> None:
        self.tray_return_points = [
            (self.width - 190.0, self.top_walkway_y - 35.0, 120.0, 70.0),
        ]

    def _spawn_due_students(self) -> None:
        remaining_total = self.config.total_student_count - self.spawned_students
        if remaining_total <= 0:
            return

        remaining_capacity = self.config.max_active_students - self._active_student_count()
        if remaining_capacity <= 0:
            return

        target_spawned = self._target_spawned_students()
        due_count = min(
            max(0, target_spawned - self.spawned_students),
            remaining_total,
            remaining_capacity,
        )
        for _ in range(due_count):
            self._spawn_student()

    def _target_spawned_students(self) -> int:
        duration = self.config.duration_game_seconds
        if duration <= 0:
            return self.config.total_student_count

        progress = clamp(self.game_time / duration, 0.0, 1.0)
        if progress <= 0.5:
            distribution = 2.0 * progress * progress
        else:
            distribution = 1.0 - 2.0 * (1.0 - progress) * (1.0 - progress)
        return min(self.config.total_student_count, round(distribution * self.config.total_student_count))

    def _spawn_student(self) -> None:
        meat_pref = self.rng.uniform(0.0, 1.0)
        veg_pref = self.rng.uniform(0.0, 1.0)
        student = Student(
            id=self.next_student_id,
            meat_pref=meat_pref,
            veg_pref=veg_pref,
            appetite=self.rng.uniform(0.8, 1.8),
            eat_speed=self.rng.uniform(0.028, 0.075),
            hesitation_time=self.rng.uniform(10.0, 28.0),
            table_walk_time=self.rng.uniform(35.0, 70.0),
            spawn_time=self.game_time,
            x=self.door[0] + self.rng.uniform(-6.0, 6.0),
            y=self.door[1] + self.rng.uniform(-6.0, 6.0),
            target_x=self.door[0] + self.rng.uniform(12.0, 55.0),
            target_y=self.door[1] + self.rng.uniform(5.0, 55.0),
            walk_speed=self.rng.uniform(8.0, 14.0),
        )
        student.decision_done_at = self.game_time + student.hesitation_time
        student.stall_id = self._choose_best_stall(student)
        self.students[student.id] = student
        self.next_student_id += 1
        self.spawned_students += 1

    def _choose_best_stall(self, student: Student) -> int:
        best_stall = min(
            self.stalls,
            key=lambda stall: (
                manhattan_2d(student.meat_pref, student.veg_pref, stall.meat_ratio, stall.veg_ratio),
                len(stall.queue),
            ),
        )
        return best_stall.id

    def _complete_ready_food(self) -> None:
        for stall in self.stalls:
            while stall.ready_times and stall.ready_times[0][1] <= self.game_time:
                student_id, ready_at = stall.ready_times.pop(0)
                if stall.queue and stall.queue[0] == student_id:
                    stall.queue.pop(0)
                elif student_id in stall.queue:
                    stall.queue.remove(student_id)

                student = self.students.get(student_id)
                if student is None or student.state == StudentState.DONE:
                    continue
                student.food_ready_at = ready_at
                student.state = StudentState.SEARCHING_SEAT

    def _update_students(self, game_delta: float) -> None:
        to_remove: list[int] = []
        for student in list(self.students.values()):
            if student.state == StudentState.DECIDING:
                if self.game_time >= student.decision_done_at:
                    student.state = StudentState.MOVING_TO_QUEUE
                    self._start_queue_path(student)
                else:
                    self._wander_near_door(student, game_delta)
            elif student.state == StudentState.MOVING_TO_QUEUE:
                arrived = self._move_student(student, game_delta, student.walk_speed)
                if arrived:
                    self._join_stall_queue(student)
            elif student.state == StudentState.QUEUED:
                self._set_queue_target(student)
                self._move_student(student, game_delta, student.walk_speed)
            elif student.state == StudentState.SEARCHING_SEAT:
                self._send_student_to_table(student)
            elif student.state == StudentState.WAITING_SEAT:
                self._send_student_to_table(student)
                self._move_student(student, game_delta, student.walk_speed)
            elif student.state == StudentState.MOVING_TO_SEAT:
                arrived = self._move_student(student, game_delta, student.table_walk_speed)
                if arrived:
                    self._occupy_reserved_seat(student)
                    student.state = StudentState.EATING
                    student.eating_done_at = self.game_time + student.eating_time
            elif student.state == StudentState.EATING:
                if student.eating_done_at is not None and self.game_time >= student.eating_done_at:
                    self._release_seat(student)
                    self._set_tray_return_path(student)
                    student.state = StudentState.MOVING_TO_TRAY_RETURN
                    self.served_students += 1
            elif student.state == StudentState.MOVING_TO_TRAY_RETURN:
                arrived = self._move_student(student, game_delta, student.walk_speed)
                if arrived or self._is_inside_tray_return(student):
                    self._set_exit_path(student)
                    student.state = StudentState.LEAVING
            elif student.state == StudentState.LEAVING:
                arrived = self._move_student(student, game_delta, student.walk_speed * 0.95)
                if arrived or self._is_inside_exit(student):
                    student.state = StudentState.DONE
                    to_remove.append(student.id)

        for student_id in to_remove:
            self.students.pop(student_id, None)

    def _wander_near_door(self, student: Student, game_delta: float) -> None:
        if distance(student.x, student.y, student.target_x, student.target_y) < 4.0:
            student.target_x = self.door[0] + self.rng.uniform(12.0, 58.0)
            student.target_y = self.door[1] + self.rng.uniform(4.0, 58.0)
        self._move_student(student, game_delta, student.walk_speed * 0.2)

    def _queue_target_position(self, student: Student) -> tuple[float, float] | None:
        if student.stall_id is None:
            return None
        stall = self.stalls[student.stall_id]
        if student.id in stall.queue:
            index = stall.queue.index(student.id)
        else:
            index = len(stall.queue)
        return stall.x, stall.y + 76.0 + index * 24.0

    def _start_queue_path(self, student: Student) -> None:
        target = self._queue_target_position(student)
        if target is None or student.stall_id is None:
            return
        stall = self.stalls[student.stall_id]
        target_x, target_y = target
        self._set_path(
            student,
            [
                (student.x, self.queue_walkway_y),
                (stall.x, self.queue_walkway_y),
                (target_x, target_y),
            ],
        )

    def _set_queue_target(self, student: Student) -> None:
        target = self._queue_target_position(student)
        if target is None:
            return
        target_x, target_y = target
        student.target_x = target_x
        student.target_y = target_y
        student.path.clear()

    def _join_stall_queue(self, student: Student) -> None:
        if student.stall_id is None:
            return
        stall = self.stalls[student.stall_id]
        if student.id in stall.queue:
            student.state = StudentState.QUEUED
            return
        ready_at = max(self.game_time, stall.next_food_ready_time) + stall.cook_time
        stall.next_food_ready_time = ready_at
        stall.queue.append(student.id)
        stall.ready_times.append((student.id, ready_at))
        student.state = StudentState.QUEUED

    def _send_student_to_table(self, student: Student) -> None:
        free: list[tuple[Table, int]] = []
        for table in self.tables:
            for seat_index in table.free_seat_indexes():
                free.append((table, seat_index))
        if not free:
            student.state = StudentState.WAITING_SEAT
            student.target_x = self.width - 70.0
            student.target_y = self.top_walkway_y
            student.path.clear()
            return

        table, seat_index = self.rng.choice(free)
        seat = table.seats[seat_index]
        seat.status = SeatStatus.RESERVED
        seat.student_id = student.id
        student.table_id = table.id
        student.seat_index = seat_index
        seat_x, seat_y = self._seat_position(table, seat_index)
        path = self._build_table_path(student.x, student.y, table, seat_index, seat_x, seat_y)
        self._set_path(student, path)
        walk_distance = self._path_distance(student.x, student.y, path)
        student.table_walk_speed = max(6.0, walk_distance / student.table_walk_time)
        student.state = StudentState.MOVING_TO_SEAT

    def _occupy_reserved_seat(self, student: Student) -> None:
        if student.table_id is None or student.seat_index is None:
            return
        seat = self.tables[student.table_id].seats[student.seat_index]
        if seat.student_id == student.id and seat.status == SeatStatus.RESERVED:
            seat.status = SeatStatus.OCCUPIED

    def _release_seat(self, student: Student) -> None:
        if student.table_id is None or student.seat_index is None:
            return
        table = self.tables[student.table_id]
        seat = table.seats[student.seat_index]
        if seat.student_id == student.id:
            seat.status = SeatStatus.FREE
            seat.student_id = None
        student.table_id = None
        student.seat_index = None

    def _seat_position(self, table: Table, seat_index: int) -> tuple[float, float]:
        offsets = [(-30.0, -24.0), (30.0, -24.0), (-30.0, 24.0), (30.0, 24.0)]
        dx, dy = offsets[seat_index]
        return table.x + dx, table.y + dy

    def _build_table_path(
        self,
        start_x: float,
        start_y: float,
        table: Table,
        seat_index: int,
        seat_x: float,
        seat_y: float,
    ) -> list[tuple[float, float]]:
        aisle_x = self._adjacent_aisle_x(table, seat_index)
        access_y = self._seat_access_y(table, seat_index)
        main_walkway_y = self._table_walkway_y(table)
        if main_walkway_y == self.bottom_walkway_y:
            points = [
                (start_x, self.top_walkway_y),
                (aisle_x, self.top_walkway_y),
                (aisle_x, self.bottom_walkway_y),
                (aisle_x, access_y),
                (seat_x, access_y),
                (seat_x, seat_y),
            ]
        else:
            points = [
                (start_x, self.top_walkway_y),
                (aisle_x, self.top_walkway_y),
                (aisle_x, access_y),
                (seat_x, access_y),
                (seat_x, seat_y),
            ]
        return self._compact_path(points)

    def _set_exit_path(self, student: Student) -> None:
        if student.table_id is None or student.seat_index is None:
            self._set_path(
                student,
                self._compact_path(
                    [
                        (student.x, self.top_walkway_y),
                        (self.exit[0], self.top_walkway_y),
                        self.exit,
                    ]
                ),
            )
            return

        table = self.tables[student.table_id]
        aisle_x = self._adjacent_aisle_x(table, student.seat_index)
        access_y = self._seat_access_y(table, student.seat_index)
        main_walkway_y = self._table_walkway_y(table)
        self._set_path(
            student,
            self._compact_path(
                [
                    (student.x, access_y),
                    (aisle_x, access_y),
                    (aisle_x, main_walkway_y),
                    (self.exit[0], main_walkway_y),
                    self.exit,
                ]
            ),
        )

    def _set_tray_return_path(self, student: Student) -> None:
        point = self._nearest_tray_return_center(student.x, student.y)
        self._set_path(
            student,
            self._compact_path(
                [
                    (student.x, self.top_walkway_y),
                    (point[0], self.top_walkway_y),
                    point,
                ]
            ),
        )

    def _nearest_tray_return_center(self, x: float, y: float) -> tuple[float, float]:
        if not self.tray_return_points:
            return self.exit[0], self.top_walkway_y
        best = min(
            self.tray_return_points,
            key=lambda rect: distance(x, y, rect[0], rect[1]),
        )
        return best[0], best[1]

    def _table_walkway_y(self, table: Table) -> float:
        return self.bottom_walkway_y if table.y >= 520.0 else self.top_walkway_y

    def _adjacent_aisle_x(self, table: Table, seat_index: int) -> float:
        column = table.id % self.table_columns
        if seat_index in (0, 2):
            return max(92.0, table.x - 92.5 if column > 0 else 92.0)
        return min(self.width - 64.0, table.x + 92.5)

    def _seat_access_y(self, table: Table, seat_index: int) -> float:
        if seat_index in (0, 1):
            return max(self.top_walkway_y, table.y - 56.0)
        return min(self.height - 64.0, table.y + 56.0)

    def _set_path(self, student: Student, path: list[tuple[float, float]]) -> None:
        student.path = self._compact_path(path)
        if student.path:
            student.target_x, student.target_y = student.path[0]

    def _compact_path(self, path: list[tuple[float, float]]) -> list[tuple[float, float]]:
        compacted: list[tuple[float, float]] = []
        for point in path:
            if not compacted or distance(compacted[-1][0], compacted[-1][1], point[0], point[1]) > 3.0:
                compacted.append(point)
        return compacted

    def _path_distance(self, start_x: float, start_y: float, path: list[tuple[float, float]]) -> float:
        total = 0.0
        current_x = start_x
        current_y = start_y
        for point_x, point_y in path:
            total += distance(current_x, current_y, point_x, point_y)
            current_x = point_x
            current_y = point_y
        return max(1.0, total)

    def _move_student(self, student: Student, game_delta: float, speed: float) -> bool:
        if student.path:
            student.target_x, student.target_y = student.path[0]
        student.x, student.y, arrived = move_towards(
            student.x,
            student.y,
            student.target_x,
            student.target_y,
            speed * game_delta,
        )
        if arrived and student.path:
            student.path.pop(0)
            if student.path:
                student.target_x, student.target_y = student.path[0]
                return False
        return arrived

    def _separate_students(self, game_delta: float) -> None:
        movable = [
            student
            for student in self.students.values()
            if student.state not in (StudentState.EATING, StudentState.DONE)
        ]
        min_distance = 25.0
        congestion_distance = 34.0
        crowded_ids: set[int] = set()
        for _ in range(3):
            for index, first in enumerate(movable):
                for second in movable[index + 1 :]:
                    dx = second.x - first.x
                    dy = second.y - first.y
                    gap = (dx * dx + dy * dy) ** 0.5
                    if gap < congestion_distance:
                        crowded_ids.add(first.id)
                        crowded_ids.add(second.id)
                    if gap >= min_distance:
                        continue
                    if gap < 0.01:
                        dx = self.rng.uniform(-1.0, 1.0)
                        dy = self.rng.uniform(-1.0, 1.0)
                        gap = (dx * dx + dy * dy) ** 0.5

                    push = (min_distance - gap) / 2.0
                    nx = dx / gap
                    ny = dy / gap
                    first.x -= nx * push
                    first.y -= ny * push
                    second.x += nx * push
                    second.y += ny * push

                    first.x = max(28.0, min(self.width - 28.0, first.x))
                    first.y = max(28.0, min(self.height - 28.0, first.y))
                    second.x = max(28.0, min(self.width - 28.0, second.x))
                    second.y = max(28.0, min(self.height - 28.0, second.y))
            self._avoid_static_obstacles(movable)

        for student in movable:
            if student.id in crowded_ids:
                student.congestion_time += game_delta
                if student.congestion_time >= 2.8:
                    self._try_start_detour(student, movable)
                    student.congestion_time = 0.0
            else:
                student.congestion_time = max(0.0, student.congestion_time - game_delta * 1.5)

    def _avoid_static_obstacles(self, students: list[Student]) -> None:
        obstacles = self._obstacle_rects()
        for student in students:
            for left, top, right, bottom in obstacles:
                if not (left < student.x < right and top < student.y < bottom):
                    continue

                distances = [
                    (abs(student.x - left), left, student.y),
                    (abs(right - student.x), right, student.y),
                    (abs(student.y - top), student.x, top),
                    (abs(bottom - student.y), student.x, bottom),
                ]
                _, new_x, new_y = min(distances, key=lambda item: item[0])
                student.x = max(28.0, min(self.width - 28.0, new_x))
                student.y = max(28.0, min(self.height - 28.0, new_y))

    def _obstacle_rects(self) -> list[tuple[float, float, float, float]]:
        rects: list[tuple[float, float, float, float]] = []
        for stall in self.stalls:
            rects.append((stall.x - 47.0, stall.y - 36.0, stall.x + 47.0, stall.y + 40.0))
        for table in self.tables:
            rects.append((table.x - 22.0, table.y - 14.0, table.x + 22.0, table.y + 14.0))
        return rects

    def _try_start_detour(self, student: Student, students: list[Student]) -> None:
        if self.game_time < student.detour_until:
            return
        if student.state in (StudentState.QUEUED, StudentState.EATING, StudentState.DONE):
            return

        original_path = list(student.path) if student.path else [(student.target_x, student.target_y)]
        candidate = self._find_detour_point(student, students)
        if candidate is None:
            return

        student.path = self._compact_path([candidate, *original_path])
        student.target_x, student.target_y = student.path[0]
        student.detour_until = self.game_time + 5.0

    def _find_detour_point(
        self,
        student: Student,
        students: list[Student],
    ) -> tuple[float, float] | None:
        dx = student.target_x - student.x
        dy = student.target_y - student.y
        gap = (dx * dx + dy * dy) ** 0.5
        if gap < 1.0:
            dx, dy, gap = 1.0, 0.0, 1.0

        nx = -dy / gap
        ny = dx / gap
        forward_x = dx / gap
        forward_y = dy / gap
        candidates: list[tuple[float, float]] = []
        for side in (1.0, -1.0):
            for side_step in (54.0, 78.0, 102.0):
                candidates.append((student.x + nx * side * side_step, student.y + ny * side * side_step))

        self.rng.shuffle(candidates)
        for point in candidates:
            if self._is_walkable_point(point[0], point[1], students, ignored_student_id=student.id):
                return point
        return None

    def _is_walkable_point(
        self,
        x: float,
        y: float,
        students: list[Student],
        ignored_student_id: int | None = None,
    ) -> bool:
        margin = 30.0
        if x < margin or x > self.width - margin or y < margin or y > self.height - margin:
            return False
        for left, top, right, bottom in self._obstacle_rects():
            if left - 18.0 <= x <= right + 18.0 and top - 18.0 <= y <= bottom + 18.0:
                return False
        for other in students:
            if other.id == ignored_student_id:
                continue
            if distance(x, y, other.x, other.y) < 38.0:
                return False
        return True

    def _is_inside_exit(self, student: Student) -> bool:
        left, top, right, bottom = self._exit_rect()
        return left <= student.x <= right and top <= student.y <= bottom

    def _is_inside_tray_return(self, student: Student) -> bool:
        for center_x, center_y, width, height in self.tray_return_points:
            left = center_x - width / 2.0
            right = center_x + width / 2.0
            top = center_y - height / 2.0
            bottom = center_y + height / 2.0
            if left <= student.x <= right and top <= student.y <= bottom:
                return True
        return False

    def _exit_rect(self) -> tuple[float, float, float, float]:
        x, y = self.exit
        return x - 58.0, y - 58.0, x + 58.0, y + 58.0

    def _active_student_count(self) -> int:
        return sum(1 for student in self.students.values() if student.state != StudentState.DONE)

    def _build_frame(self) -> dict[str, Any]:
        return {
            "game_time": min(self.game_time, self.config.duration_game_seconds),
            "duration": self.config.duration_game_seconds,
            "time_scale": self.time_scale,
            "spawned_students": self.spawned_students,
            "served_students": self.served_students,
            "active_students": self._active_student_count(),
            "door": self.door,
            "exit": self.exit,
            "tray_return_points": [
                {
                    "id": index,
                    "x": center_x,
                    "y": center_y,
                    "width": width,
                    "height": height,
                    "is_congested": False,
                }
                for index, (center_x, center_y, width, height) in enumerate(self.tray_return_points)
            ],
            "width": self.width,
            "height": self.height,
            "stats": {
                "avg_wait_time": None,
                "avg_total_time": None,
                "max_active_students": self.max_active_students_seen,
                "stall_queue_stats": [
                    {
                        "stall_id": stall.id,
                        "max_queue_length": len(stall.queue),
                    }
                    for stall in self.stalls
                ],
                "seat_utilization": None,
            },
            "walk_paths": self._build_walk_paths(),
            "stalls": [
                {
                    "id": stall.id,
                    "x": stall.x,
                    "y": stall.y,
                    "meat_ratio": stall.meat_ratio,
                    "veg_ratio": stall.veg_ratio,
                    "cook_time": stall.cook_time,
                    "cook_remaining": self._stall_cook_remaining(stall),
                    "cook_progress": self._stall_cook_progress(stall),
                    "queue_count": len(stall.queue),
                }
                for stall in self.stalls
            ],
            "tables": [
                {
                    "id": table.id,
                    "x": table.x,
                    "y": table.y,
                    "occupied": table.occupied_count,
                    "seats": [seat.student_id for seat in table.seats],
                    "seat_frames": [
                        {
                            "index": seat_index,
                            "status": seat.status.value,
                            "student_id": seat.student_id,
                        }
                        for seat_index, seat in enumerate(table.seats)
                    ],
                }
                for table in self.tables
            ],
            "students": [
                {
                    "id": student.id,
                    "x": student.x,
                    "y": student.y,
                    "target_x": student.target_x,
                    "target_y": student.target_y,
                    "path": list(student.path),
                    "state": student.state.value,
                    "meat_pref": student.meat_pref,
                    "veg_pref": student.veg_pref,
                    "stall_id": student.stall_id,
                    "table_id": student.table_id,
                    "seat_index": student.seat_index,
                }
                for student in self.students.values()
                if student.state != StudentState.DONE
            ],
        }

    def _stall_cook_remaining(self, stall: Stall) -> float:
        if not stall.ready_times:
            return 0.0
        return max(0.0, stall.ready_times[0][1] - self.game_time)

    def _stall_cook_progress(self, stall: Stall) -> float:
        if not stall.ready_times or stall.cook_time <= 0:
            return 0.0
        remaining = self._stall_cook_remaining(stall)
        return max(0.0, min(1.0, 1.0 - remaining / stall.cook_time))

    def _build_walk_paths(self) -> list[dict[str, Any]]:
        left = 70.0
        right = self.width - 40.0
        aisle_xs = sorted(
            {
                round(max(92.0, table.x - 92.5), 1)
                for table in self.tables
            }
            | {
                round(min(self.width - 64.0, table.x + 92.5), 1)
                for table in self.tables
            }
        )
        paths: list[dict[str, Any]] = [
            {"kind": "queue", "points": [(left, self.queue_walkway_y), (right, self.queue_walkway_y)]},
            {"kind": "top", "points": [(left, self.top_walkway_y), (right, self.top_walkway_y)]},
            {"kind": "bottom", "points": [(left, self.bottom_walkway_y), (right, self.bottom_walkway_y)]},
            {"kind": "door", "points": [self.door, (self.door[0], self.queue_walkway_y)]},
            {"kind": "exit", "points": [(self.exit[0], self.bottom_walkway_y), self.exit]},
        ]
        for aisle_x in aisle_xs:
            paths.append(
                {
                    "kind": "aisle",
                    "points": [(aisle_x, self.top_walkway_y), (aisle_x, self.bottom_walkway_y)],
                }
            )
        return paths
