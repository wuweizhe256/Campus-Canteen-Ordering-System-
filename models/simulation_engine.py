from __future__ import annotations

import random
import time
from math import hypot
from typing import Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from models.data_recorder import DataRecorder, EventRecordP0
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
        self.queue_walkway_y = 156.0
        self.top_walkway_y = 260.0
        self.bottom_walkway_y = 724.0
        self.door = (58.0, 112.0)
        self.exit = (1224.0, 710.0)
        self.tray_return_points: list[tuple[float, float, float, float]] = []
        self.stalls: list[Stall] = []
        self.tables: list[Table] = []
        self.students: dict[int, Student] = {}
        self.game_time = 0.0
        self.next_student_id = 1
        self.spawned_students = 0
        self.served_students = 0
        self.max_active_students_seen = 0
        self.data_recorder = DataRecorder()
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
        self.data_recorder = DataRecorder(
            total_seats=sum(len(table.seats) for table in self.tables),
            duration=self.config.duration_game_seconds,
        )

    def _build_stalls(self) -> None:
        self.stalls.clear()
        count = max(1, self.config.stall_count)
        left = 160.0
        right = self.width - 170.0
        gap = 0.0 if count == 1 else (right - left) / (count - 1)
        for index in range(count):
            self.stalls.append(
                Stall(
                    id=index,
                    x=left + gap * index,
                    y=86.0,
                    meat_ratio=self.rng.uniform(0.0, 1.0),
                    veg_ratio=self.rng.uniform(0.0, 1.0),
                    cook_time=self.rng.uniform(12.0, 28.0),
                )
            )

    def _build_tables(self) -> None:
        self.tables.clear()
        count = max(1, self.config.table_count)
        start_x = 190.0
        start_y = 372.0
        gap_x = 172.0
        gap_y = 118.0
        for index in range(count):
            row = index // self.table_columns
            column = index % self.table_columns
            stagger = 22.0 if row % 2 else 0.0
            self.tables.append(
                Table(
                    id=index,
                    x=start_x + column * gap_x + stagger,
                    y=start_y + row * gap_y,
                )
            )

    def _build_tray_return_points(self) -> None:
        self.tray_return_points = [
            (self.width - 82.0, 548.0, 136.0, 96.0),
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
        self._record_student_event(
            "student_spawned",
            student,
            from_state=None,
            to_state=student.state,
        )

    def _choose_best_stall(self, student: Student) -> int:
        def score(stall: Stall) -> float:
            taste_cost = manhattan_2d(student.meat_pref, student.veg_pref, stall.meat_ratio, stall.veg_ratio) * 90.0
            queue_cost = len(stall.queue) * 32.0
            travel_cost = distance(student.x, student.y, stall.x, self.queue_walkway_y) * 0.18
            congestion_cost = self._density_near(stall.x, stall.y + 110.0, 105.0) * 22.0
            ready_bonus = self._stall_cook_progress(stall) * 16.0 if stall.ready_times else 0.0
            return taste_cost + queue_cost + travel_cost + congestion_cost - ready_bonus

        return min(self.stalls, key=score).id

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
                previous_state = student.state
                student.food_ready_at = ready_at
                student.state = StudentState.SEARCHING_SEAT
                self._record_student_event(
                    "food_ready",
                    student,
                    game_time=ready_at,
                    from_state=previous_state,
                    to_state=student.state,
                )

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
                    previous_state = student.state
                    student.state = StudentState.EATING
                    student.eating_done_at = self.game_time + student.eating_time
                    self._record_student_event(
                        "eating_started",
                        student,
                        from_state=previous_state,
                        to_state=student.state,
                    )
            elif student.state == StudentState.EATING:
                if student.eating_done_at is not None and self.game_time >= student.eating_done_at:
                    previous_state = student.state
                    self._record_student_event(
                        "eating_finished",
                        student,
                        from_state=previous_state,
                        to_state=StudentState.MOVING_TO_TRAY_RETURN,
                    )
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
                    previous_state = student.state
                    student.state = StudentState.DONE
                    self._record_student_event(
                        "student_left",
                        student,
                        from_state=previous_state,
                        to_state=student.state,
                    )
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
        entry_x = min(max(student.x + 90.0, 92.0), self.width - 92.0)
        self._set_path(
            student,
            [
                (entry_x, self.queue_walkway_y),
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
        previous_state = student.state
        student.state = StudentState.QUEUED
        self._record_student_event(
            "queue_started",
            student,
            from_state=previous_state,
            to_state=student.state,
        )

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

        table, seat_index, path, walk_distance = self._best_seat_candidate(student, free)
        seat = table.seats[seat_index]
        seat.status = SeatStatus.RESERVED
        seat.student_id = student.id
        student.table_id = table.id
        student.seat_index = seat_index
        self._set_path(student, path)
        student.table_walk_speed = max(6.0, walk_distance / student.table_walk_time)
        student.state = StudentState.MOVING_TO_SEAT

    def _best_seat_candidate(
        self,
        student: Student,
        free: list[tuple[Table, int]],
    ) -> tuple[Table, int, list[tuple[float, float]], float]:
        best: tuple[float, Table, int, list[tuple[float, float]], float] | None = None
        for table, seat_index in free:
            seat_x, seat_y = self._seat_position(table, seat_index)
            path = self._build_table_path(student.x, student.y, table, seat_index, seat_x, seat_y)
            walk_distance = self._path_distance(student.x, student.y, path)
            table_density = self._density_near(table.x, table.y, 92.0)
            tray_distance = distance(seat_x, seat_y, *self._nearest_tray_return_center(seat_x, seat_y))
            occupied_bias = table.occupied_count * 18.0
            jitter = self.rng.uniform(0.0, 6.0)
            score = walk_distance + table_density * 55.0 + tray_distance * 0.08 + occupied_bias + jitter
            if best is None or score < best[0]:
                best = (score, table, seat_index, path, walk_distance)
        assert best is not None
        return best[1], best[2], best[3], best[4]

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
        offsets = [(-50.0, -42.0), (50.0, -42.0), (-50.0, 42.0), (50.0, 42.0)]
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
            staging_x = self.width - 155.0
            self._set_path(
                student,
                self._compact_path(
                    [
                        (staging_x, student.y),
                        (staging_x, self.bottom_walkway_y),
                        (self.exit[0], self.bottom_walkway_y),
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
                    (self.width - 155.0, main_walkway_y),
                    (self.width - 155.0, self.bottom_walkway_y),
                    (self.exit[0], self.bottom_walkway_y),
                    self.exit,
                ]
            ),
        )

    def _set_tray_return_path(self, student: Student) -> None:
        point = self._nearest_tray_return_center(student.x, student.y)
        main_walkway_y = self.bottom_walkway_y if student.y >= 520.0 else self.top_walkway_y
        staging_x = self.width - 155.0
        self._set_path(
            student,
            self._compact_path(
                [
                    (student.x, main_walkway_y),
                    (staging_x, main_walkway_y),
                    (staging_x, point[1]),
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

    def _student_foot_point(self, student: Student) -> tuple[float, float]:
        return student.x, student.y + 14.0

    def _foot_point_from_position(self, x: float, y: float) -> tuple[float, float]:
        return x, y + 14.0

    def _move_student(self, student: Student, game_delta: float, speed: float) -> bool:
        if student.path:
            student.target_x, student.target_y = student.path[0]

        old_x, old_y = student.x, student.y
        target_distance = distance(student.x, student.y, student.target_x, student.target_y)
        if target_distance <= max(4.0, speed * game_delta * 0.7):
            student.x, student.y = student.target_x, student.target_y
            arrived = True
        else:
            vx, vy = self._desired_velocity(student, speed)
            vx, vy = self._apply_neighbor_avoidance(student, vx, vy, speed)
            vx, vy = self._apply_obstacle_avoidance(student, vx, vy, speed)
            vx, vy = self._limit_velocity(vx, vy, speed)
            foot_x, foot_y = self._student_foot_point(student)
            near_count = self._neighbor_count(foot_x, foot_y, 58.0, ignored_student_id=student.id)
            speed_factor = 1.0 / (1.0 + near_count * 0.12)
            next_x = student.x + vx * game_delta * speed_factor
            next_y = student.y + vy * game_delta * speed_factor
            if self._is_walkable_point(next_x, next_y, list(self.students.values()), ignored_student_id=student.id):
                student.x = next_x
                student.y = next_y
            else:
                student.x, student.y, _ = move_towards(
                    student.x,
                    student.y,
                    student.target_x,
                    student.target_y,
                    speed * game_delta * 0.35,
                )
            student.x = max(28.0, min(self.width - 28.0, student.x))
            student.y = max(28.0, min(self.height - 28.0, student.y))
            arrived = distance(student.x, student.y, student.target_x, student.target_y) <= 5.0

        moved = distance(old_x, old_y, student.x, student.y)
        student.actual_speed = moved / game_delta if game_delta > 0 else 0.0
        if moved > 0.2:
            student.facing_x = (student.x - old_x) / moved
            student.facing_y = (student.y - old_y) / moved
        if target_distance > 18.0 and student.actual_speed < max(1.2, speed * 0.18):
            student.stuck_time += game_delta
        else:
            student.stuck_time = max(0.0, student.stuck_time - game_delta * 1.8)
        student.last_x = student.x
        student.last_y = student.y

        if arrived and student.path:
            student.path.pop(0)
            if student.path:
                student.target_x, student.target_y = student.path[0]
                return False
        return arrived

    def _desired_velocity(self, student: Student, speed: float) -> tuple[float, float]:
        dx = student.target_x - student.x
        dy = student.target_y - student.y
        gap = hypot(dx, dy)
        if gap < 0.01:
            return 0.0, 0.0
        return dx / gap * speed, dy / gap * speed

    def _apply_neighbor_avoidance(
        self,
        student: Student,
        vx: float,
        vy: float,
        speed: float,
    ) -> tuple[float, float]:
        desired_x = vx
        desired_y = vy
        foot_x, foot_y = self._student_foot_point(student)
        for other in self.students.values():
            if other.id == student.id or other.state in (StudentState.EATING, StudentState.DONE):
                continue
            other_foot_x, other_foot_y = self._student_foot_point(other)
            dx = foot_x - other_foot_x
            dy = foot_y - other_foot_y
            gap = max(1.0, hypot(dx, dy))
            if gap > 76.0:
                continue
            ahead = (other_foot_x - foot_x) * student.facing_x + (other_foot_y - foot_y) * student.facing_y
            strength = ((76.0 - gap) / 76.0) ** 2 * speed * 1.65
            desired_x += dx / gap * strength
            desired_y += dy / gap * strength
            if ahead > 0 and gap < 52.0:
                side = 1.0 if (student.id + other.id) % 2 == 0 else -1.0
                desired_x += -student.facing_y * speed * 0.36 * side
                desired_y += student.facing_x * speed * 0.36 * side
        return desired_x, desired_y

    def _apply_obstacle_avoidance(
        self,
        student: Student,
        vx: float,
        vy: float,
        speed: float,
    ) -> tuple[float, float]:
        desired_x = vx
        desired_y = vy
        foot_x, foot_y = self._student_foot_point(student)
        padding = 42.0
        for left, top, right, bottom in self._obstacle_rects():
            nearest_x = min(max(foot_x, left), right)
            nearest_y = min(max(foot_y, top), bottom)
            dx = foot_x - nearest_x
            dy = foot_y - nearest_y
            gap = hypot(dx, dy)
            if left - padding <= foot_x <= right + padding and top - padding <= foot_y <= bottom + padding:
                if gap < 0.01:
                    center_x = (left + right) / 2.0
                    center_y = (top + bottom) / 2.0
                    dx = foot_x - center_x or 1.0
                    dy = foot_y - center_y or 1.0
                    gap = hypot(dx, dy)
                strength = ((padding - min(padding, gap)) / padding + 0.22) * speed * 1.15
                desired_x += dx / gap * strength
                desired_y += dy / gap * strength
        wall_margin = 48.0
        if student.x < wall_margin:
            desired_x += speed * (wall_margin - student.x) / wall_margin
        elif student.x > self.width - wall_margin:
            desired_x -= speed * (student.x - (self.width - wall_margin)) / wall_margin
        if student.y < wall_margin:
            desired_y += speed * (wall_margin - student.y) / wall_margin
        elif student.y > self.height - wall_margin:
            desired_y -= speed * (student.y - (self.height - wall_margin)) / wall_margin
        return desired_x, desired_y

    def _limit_velocity(self, vx: float, vy: float, speed: float) -> tuple[float, float]:
        gap = hypot(vx, vy)
        max_speed = speed * 1.18
        if gap <= max_speed or gap < 0.01:
            return vx, vy
        return vx / gap * max_speed, vy / gap * max_speed

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
                    first_foot_x, first_foot_y = self._student_foot_point(first)
                    second_foot_x, second_foot_y = self._student_foot_point(second)
                    dx = second_foot_x - first_foot_x
                    dy = second_foot_y - first_foot_y
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
                student.congestion_time += game_delta * 0.45
            elif student.stuck_time >= 1.8:
                student.congestion_time += game_delta
            else:
                student.congestion_time = max(0.0, student.congestion_time - game_delta * 1.5)

            if student.stuck_time >= 3.2 and student.congestion_time >= 1.2:
                self._try_start_detour(student, movable)
                student.congestion_time = 0.0

    def _avoid_static_obstacles(self, students: list[Student]) -> None:
        obstacles = self._obstacle_rects()
        for student in students:
            foot_x, foot_y = self._student_foot_point(student)
            for left, top, right, bottom in obstacles:
                if not (left < foot_x < right and top < foot_y < bottom):
                    continue

                distances = [
                    (abs(foot_x - left), left, foot_y),
                    (abs(right - foot_x), right, foot_y),
                    (abs(foot_y - top), foot_x, top),
                    (abs(bottom - foot_y), foot_x, bottom),
                ]
                _, new_foot_x, new_foot_y = min(distances, key=lambda item: item[0])
                student.x = max(28.0, min(self.width - 28.0, new_foot_x))
                student.y = max(28.0, min(self.height - 28.0, new_foot_y - 14.0))
                foot_x, foot_y = self._student_foot_point(student)

    def _obstacle_rects(self) -> list[tuple[float, float, float, float]]:
        rects: list[tuple[float, float, float, float]] = []
        for stall in self.stalls:
            rects.append((stall.x - 66.0, stall.y - 52.0, stall.x + 66.0, stall.y + 62.0))
        for table in self.tables:
            rects.append((table.x - 48.0, table.y - 22.0, table.x + 48.0, table.y + 22.0))
        return rects

    def _try_start_detour(self, student: Student, students: list[Student]) -> None:
        if self.game_time < student.detour_until:
            return
        if student.state in (StudentState.QUEUED, StudentState.EATING, StudentState.DONE):
            return

        if self._reroute_student(student):
            student.reroute_count += 1
            student.detour_until = self.game_time + 3.0
            student.stuck_time = 0.0
            return

        original_path = list(student.path) if student.path else [(student.target_x, student.target_y)]
        candidate = self._find_detour_point(student, students)
        if candidate is None:
            return

        student.path = self._compact_path([candidate, *original_path])
        student.target_x, student.target_y = student.path[0]
        student.reroute_count += 1
        student.detour_until = self.game_time + 4.0
        student.stuck_time = 0.0

    def _reroute_student(self, student: Student) -> bool:
        if student.state == StudentState.MOVING_TO_QUEUE:
            before = list(student.path)
            self._start_queue_path(student)
            return bool(student.path) and student.path != before
        if student.state == StudentState.MOVING_TO_SEAT and student.table_id is not None and student.seat_index is not None:
            table = self.tables[student.table_id]
            seat_x, seat_y = self._seat_position(table, student.seat_index)
            path = self._build_table_path(student.x, student.y, table, student.seat_index, seat_x, seat_y)
            self._set_path(student, path)
            return bool(student.path)
        if student.state == StudentState.MOVING_TO_TRAY_RETURN:
            self._set_tray_return_path(student)
            return bool(student.path)
        if student.state == StudentState.LEAVING:
            self._set_exit_path(student)
            return bool(student.path)
        return False

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
        foot_x, foot_y = self._foot_point_from_position(x, y)
        if foot_x < margin or foot_x > self.width - margin or foot_y < margin or foot_y > self.height - margin:
            return False
        for left, top, right, bottom in self._obstacle_rects():
            if left - 14.0 <= foot_x <= right + 14.0 and top - 14.0 <= foot_y <= bottom + 14.0:
                return False
        for other in students:
            if other.id == ignored_student_id:
                continue
            other_foot_x, other_foot_y = self._student_foot_point(other)
            if distance(foot_x, foot_y, other_foot_x, other_foot_y) < 28.0:
                return False
        return True

    def _is_inside_exit(self, student: Student) -> bool:
        left, top, right, bottom = self._exit_rect()
        foot_x, foot_y = self._student_foot_point(student)
        return left <= foot_x <= right and top <= foot_y <= bottom

    def _is_inside_tray_return(self, student: Student) -> bool:
        foot_x, foot_y = self._student_foot_point(student)
        for center_x, center_y, width, height in self.tray_return_points:
            left = center_x - width / 2.0
            right = center_x + width / 2.0
            top = center_y - height / 2.0
            bottom = center_y + height / 2.0
            if left <= foot_x <= right and top <= foot_y <= bottom:
                return True
        return False

    def _exit_rect(self) -> tuple[float, float, float, float]:
        x, y = self.exit
        return x - 58.0, y - 58.0, x + 58.0, y + 58.0

    def _active_student_count(self) -> int:
        return sum(1 for student in self.students.values() if student.state != StudentState.DONE)

    def _neighbor_count(self, x: float, y: float, radius: float, ignored_student_id: int | None = None) -> int:
        return sum(
            1
            for student in self.students.values()
            if student.id != ignored_student_id
            and student.state not in (StudentState.EATING, StudentState.DONE)
            and distance(x, y, *self._student_foot_point(student)) <= radius
        )

    def _density_near(self, x: float, y: float, radius: float) -> int:
        return self._neighbor_count(x, y, radius)

    def _tray_return_density(self, x: float, y: float) -> int:
        return sum(
            1
            for student in self.students.values()
            if student.state == StudentState.MOVING_TO_TRAY_RETURN and distance(x, y, *self._student_foot_point(student)) <= 110.0
        )

    def _record_student_event(
        self,
        event_type: str,
        student: Student,
        from_state: StudentState | str | None,
        to_state: StudentState | str | None,
        game_time: float | None = None,
    ) -> None:
        self.data_recorder.record_event(
            EventRecordP0(
                event_type=event_type,
                game_time=self.game_time if game_time is None else game_time,
                student_id=student.id,
                stall_id=student.stall_id,
                table_id=student.table_id,
                seat_index=student.seat_index,
                from_state=_state_value(from_state),
                to_state=_state_value(to_state),
            )
        )

    def _record_queue_samples(self) -> None:
        for stall in self.stalls:
            self.data_recorder.record_queue_sample(self.game_time, stall.id, len(stall.queue))

    def _record_runtime_sample(self) -> None:
        active = [student for student in self.students.values() if student.state != StudentState.DONE]
        moving = [
            student
            for student in active
            if student.state not in (StudentState.EATING, StudentState.QUEUED)
        ]
        avg_move_speed = _average_float(student.actual_speed for student in moving) if moving else None
        density_load = sum(max(0, self._neighbor_count(*self._student_foot_point(student), 58.0, student.id) - 1) for student in active)
        congestion_index = min(1.0, density_load / max(1.0, len(active) * 3.0)) if active else 0.0
        stuck_student_count = sum(
            1
            for student in moving
            if student.stuck_time >= 1.6 or (student.actual_speed < 1.0 and distance(student.x, student.y, student.target_x, student.target_y) > 18.0)
        )
        reroute_count = sum(student.reroute_count for student in active)
        avg_queue_length = _average_float(len(stall.queue) for stall in self.stalls) if self.stalls else None
        tray_return_queue_length = sum(
            1
            for student in active
            if student.state == StudentState.MOVING_TO_TRAY_RETURN
            and distance(*self._student_foot_point(student), *self._nearest_tray_return_center(student.x, student.y)) <= 96.0
        )
        self.data_recorder.record_runtime_sample(
            self.game_time,
            avg_move_speed,
            congestion_index,
            stuck_student_count,
            reroute_count,
            avg_queue_length,
            tray_return_queue_length,
        )

    def _build_frame(self) -> dict[str, Any]:
        self._record_queue_samples()
        self._record_runtime_sample()
        stats = self.data_recorder.build_stats(current_time=self.game_time).to_dict()
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
                    "is_congested": self._tray_return_density(center_x, center_y) >= 4,
                }
                for index, (center_x, center_y, width, height) in enumerate(self.tray_return_points)
            ],
            "width": self.width,
            "height": self.height,
            "stats": stats,
            "walk_paths": self._build_walk_paths(),
            "collision_boxes": self._build_collision_boxes(),
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
                    "actual_speed": student.actual_speed,
                    "stuck_time": student.stuck_time,
                    "reroute_count": student.reroute_count,
                    "facing_x": student.facing_x,
                    "facing_y": student.facing_y,
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

    def _build_collision_boxes(self) -> list[dict[str, float]]:
        boxes: list[dict[str, float]] = []
        for left, top, right, bottom in self._obstacle_rects():
            boxes.append(
                {
                    "x": (left + right) / 2.0,
                    "y": (top + bottom) / 2.0,
                    "width": right - left,
                    "height": bottom - top,
                }
            )
        return boxes

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
        tray_point = self._nearest_tray_return_center(self.width, self.height / 2.0)
        paths: list[dict[str, Any]] = [
            {"kind": "queue", "points": [(left, self.queue_walkway_y), (right, self.queue_walkway_y)]},
            {"kind": "top", "points": [(left, self.top_walkway_y), (right, self.top_walkway_y)]},
            {"kind": "bottom", "points": [(left, self.bottom_walkway_y), (right, self.bottom_walkway_y)]},
            {"kind": "door", "points": [self.door, (self.door[0] + 90.0, self.queue_walkway_y)]},
            {"kind": "tray", "points": [(self.width - 155.0, self.top_walkway_y), (self.width - 155.0, tray_point[1]), tray_point]},
            {"kind": "exit", "points": [(self.width - 155.0, self.bottom_walkway_y), (self.exit[0], self.bottom_walkway_y), self.exit]},
        ]
        for aisle_x in aisle_xs:
            paths.append(
                {
                    "kind": "aisle",
                    "points": [(aisle_x, self.top_walkway_y), (aisle_x, self.bottom_walkway_y)],
                }
            )
        return paths


def _state_value(state: StudentState | str | None) -> str | None:
    if state is None:
        return None
    if isinstance(state, StudentState):
        return state.value
    return str(state)


def _average_float(values: Any) -> float | None:
    samples = [float(value) for value in values]
    if not samples:
        return None
    return sum(samples) / len(samples)
