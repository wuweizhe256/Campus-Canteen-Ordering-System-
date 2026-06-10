from __future__ import annotations

import json
import random
import time
from math import hypot
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from models.data_recorder import DataRecorder, EventRecordP0
from models.entities import (
    Dish,
    Entrance,
    Exit,
    Order,
    OrderStatus,
    RunSummary,
    SeatStatus,
    SimulationConfig,
    Stall,
    StallStatus,
    Student,
    StudentState,
    Table,
)
from models.pathfinding import Doorway, GridPathFinder, NavRect
from utils.helpers import clamp, distance, manhattan_2d, move_towards

MENU_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "menu.json"
MAX_SEAT_WAIT_SECONDS = 180.0


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
        self.entrances: list[Entrance] = []
        self.entrance_flow_counts: dict[int, int] = {}
        self.exits: list[Exit] = []
        self.exit_flow_counts: dict[int, int] = {}
        self.tray_return_points: list[tuple[float, float, float, float]] = []
        self.stalls: list[Stall] = []
        self.tables: list[Table] = []
        self.students: dict[int, Student] = {}
        self.game_time = 0.0
        self.next_student_id = 1
        self.next_order_id = 1
        self.next_group_id = 1
        self.next_path_id = 1
        self.spawned_students = 0
        self.finished_eating_students = 0
        self.max_active_students_seen = 0
        self.data_recorder = DataRecorder()
        self.menu_config, self.issues = _load_menu_config(MENU_CONFIG_PATH)
        self._navigation_obstacle_cache: list[NavRect] | None = None
        self._navigation_pathfinder_cache: GridPathFinder | None = None
        self._navigation_doorway_cache: list[Doorway] | None = None
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
                self._refresh_orders_and_stalls()
                self._record_queue_samples()
                self._record_runtime_sample()
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
                    finished_eating_students=self.finished_eating_students,
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
        self._build_entrances()
        self._build_exits()
        self._build_stalls()
        self._build_tables()
        self._build_tray_return_points()
        self.students.clear()
        self.game_time = 0.0
        self.next_student_id = 1
        self.next_order_id = 1
        self.next_group_id = 1
        self.next_path_id = 1
        self.spawned_students = 0
        self.finished_eating_students = 0
        self.max_active_students_seen = 0
        self._navigation_obstacle_cache = None
        self._navigation_pathfinder_cache = None
        self._navigation_doorway_cache = None
        self.entrance_flow_counts = {entrance.id: 0 for entrance in self.entrances}
        self.exit_flow_counts = {exit_area.id: 0 for exit_area in self.exits}
        self.data_recorder = DataRecorder(
            total_seats=sum(len(table.seats) for table in self.tables),
            duration=self.config.duration_game_seconds,
        )
        self._record_layout_events()

    def _build_entrances(self) -> None:
        weights = list(self.config.entrance_weights or ())
        default_positions = [
            (0, 58.0, 112.0, 96.0, 104.0),
            (1, 58.0, 310.0, 96.0, 104.0),
            (2, 58.0, 560.0, 96.0, 104.0),
        ]
        if not weights:
            weights = [1.0]
        self.entrances = [
            Entrance(
                id=entrance_id,
                x=x,
                y=y,
                width=width,
                height=height,
                weight=max(0.0, float(weights[index] if index < len(weights) else 0.0)),
            )
            for index, (entrance_id, x, y, width, height) in enumerate(default_positions)
            if index < len(weights)
        ]
        if not self.entrances or all(entrance.weight <= 0 for entrance in self.entrances):
            self.entrances = [Entrance(0, self.door[0], self.door[1], 96.0, 104.0, 1.0)]
        self.door = (self.entrances[0].x, self.entrances[0].y)

    def _build_exits(self) -> None:
        self.exits = [
            Exit(0, 1224.0, 710.0, 116.0, 116.0),
            Exit(1, 1224.0, 430.0, 116.0, 116.0),
            Exit(2, 1224.0, 180.0, 116.0, 116.0),
        ]
        self.exit = (self.exits[0].x, self.exits[0].y)

    def _build_stalls(self) -> None:
        self.stalls.clear()
        count = max(1, self.config.stall_count)
        left = 160.0
        right = self.width - 170.0
        gap = 0.0 if count == 1 else (right - left) / (count - 1)
        for index in range(count):
            dishes = self._build_stall_dishes(index)
            status = StallStatus.OPEN if dishes else StallStatus.SOLD_OUT
            self.stalls.append(
                Stall(
                    id=index,
                    x=left + gap * index,
                    y=86.0,
                    meat_ratio=self.rng.uniform(0.0, 1.0),
                    veg_ratio=self.rng.uniform(0.0, 1.0),
                    cook_time=self.rng.uniform(12.0, 28.0),
                    status=status,
                    dishes=dishes,
                )
            )

    def _build_stall_dishes(self, stall_index: int) -> list[Dish]:
        menu = self.menu_config["dishes"]
        dishes_per_stall = int(self.menu_config["dishes_per_stall"])
        price_jitter = self.menu_config["price_jitter"]
        cook_time_jitter = self.menu_config["cook_time_jitter"]
        dishes: list[Dish] = []
        for offset in range(dishes_per_stall):
            dish_data = menu[(stall_index + offset * 2) % len(menu)]
            dishes.append(
                Dish(
                    id=int(dish_data["id"]),
                    name=str(dish_data["name"]),
                    features=dict(dish_data["features"]),
                    price=float(dish_data["price"]) + self.rng.uniform(*price_jitter),
                    stock=max(0, int(dish_data["stock"])),
                    cook_time=max(1.0, float(dish_data["cook_time"]) + self.rng.uniform(*cook_time_jitter)),
                )
            )
        return dishes

    def _build_tables(self) -> None:
        self.tables.clear()
        table_specs = self._table_specs()
        count = len(table_specs)
        start_x = 190.0
        start_y = 372.0
        gap_x = 172.0
        gap_y = 118.0
        for index, (table_type, seat_count) in enumerate(table_specs):
            row = index // self.table_columns
            column = index % self.table_columns
            stagger = 22.0 if row % 2 else 0.0
            self.tables.append(
                Table(
                    id=index,
                    x=start_x + column * gap_x + stagger,
                    y=start_y + row * gap_y,
                    table_type=table_type,
                    seat_count=seat_count,
                )
            )

    def _table_specs(self) -> list[tuple[str, int]]:
        seat_counts = {"two": 2, "four": 4, "six": 6}
        specs: list[tuple[str, int]] = []
        for table_type, count in self.config.resolved_table_type_counts().items():
            seat_count = seat_counts.get(table_type, 4)
            specs.extend((table_type, seat_count) for _ in range(max(0, int(count))))
        return specs or [("four", 4)]

    def _build_tray_return_points(self) -> None:
        self.tray_return_points = [
            (self.width - 82.0, 548.0, 136.0, 96.0),
        ]

    def _record_layout_events(self) -> None:
        for table in self.tables:
            self.data_recorder.record_event(
                EventRecordP0(
                    event_type="table_type_registered",
                    game_time=self.game_time,
                    table_id=table.id,
                    table_type=table.table_type,
                    seat_count=table.seat_count,
                )
            )
        for obstacle_id, obstacle in enumerate(self._obstacle_frames()):
            self.data_recorder.record_event(
                EventRecordP0(
                    event_type="obstacle_registered",
                    game_time=self.game_time,
                    obstacle_id=obstacle_id,
                    obstacle_kind=str(obstacle.get("kind") or "obstacle"),
                )
            )

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
        while due_count > 0:
            group_size = min(
                self._choose_group_size(),
                due_count,
                remaining_total,
                remaining_capacity,
            )
            self._spawn_group(group_size)
            due_count -= group_size
            remaining_total -= group_size
            remaining_capacity -= group_size

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

    def _choose_group_size(self) -> int:
        roll = self.rng.random()
        if roll < self.config.companion_multi_ratio:
            return self.rng.choice([3, 4])
        if roll < self.config.companion_multi_ratio + self.config.companion_pair_ratio:
            return 2
        return 1

    def _spawn_group(self, group_size: int) -> None:
        group_id = self.next_group_id if group_size > 1 else None
        if group_id is not None:
            self.next_group_id += 1
            self.data_recorder.record_event(
                EventRecordP0(
                    event_type="group_created",
                    game_time=self.game_time,
                    group_id=group_id,
                    group_size=group_size,
                )
            )

        meat_pref = self.rng.uniform(0.0, 1.0)
        veg_pref = self.rng.uniform(0.0, 1.0)
        shared_preferences = {
            "meat": meat_pref,
            "veg": veg_pref,
            "price_sensitivity": self.rng.uniform(0.2, 1.0),
            "wait_tolerance": self.rng.uniform(0.2, 1.0),
            "spicy": self.rng.uniform(0.0, 1.0),
        }
        entrance = self._choose_entrance()
        sample_student = self._build_student(
            meat_pref=meat_pref,
            veg_pref=veg_pref,
            preferences=dict(shared_preferences),
            group_id=group_id,
            group_size=group_size,
            member_index=0,
            entrance=entrance,
        )
        dish_id, stall_id = self._choose_dish_and_stall(sample_student)
        self._register_student(sample_student, dish_id, stall_id)
        for member_index in range(1, group_size):
            member = self._build_student(
                meat_pref=clamp(meat_pref + self.rng.uniform(-0.08, 0.08), 0.0, 1.0),
                veg_pref=clamp(veg_pref + self.rng.uniform(-0.08, 0.08), 0.0, 1.0),
                preferences=dict(shared_preferences),
                group_id=group_id,
                group_size=group_size,
                member_index=member_index,
                entrance=entrance,
            )
            self._register_student(member, dish_id, stall_id)

    def _choose_entrance(self) -> Entrance:
        available = [entrance for entrance in self.entrances if entrance.weight > 0]
        if not available:
            return self.entrances[0]
        weighted: list[tuple[Entrance, float]] = []
        for entrance in available:
            local_density = self._density_near(entrance.x, entrance.y, 130.0)
            effective_weight = entrance.weight / (1.0 + local_density * 0.22)
            weighted.append((entrance, max(0.01, effective_weight)))
        total_weight = sum(weight for _, weight in weighted)
        roll = self.rng.uniform(0.0, total_weight)
        cumulative = 0.0
        for entrance, weight in weighted:
            cumulative += weight
            if roll <= cumulative:
                return entrance
        return weighted[-1][0]

    def _build_student(
        self,
        meat_pref: float,
        veg_pref: float,
        preferences: dict[str, float],
        group_id: int | None,
        group_size: int,
        member_index: int,
        entrance: Entrance,
    ) -> Student:
        columns = max(1, min(3, group_size))
        row = member_index // columns
        column = member_index % columns
        formation_x = (column - (columns - 1) / 2.0) * 22.0
        formation_y = row * 24.0
        spawn_jitter_x = self.rng.uniform(-entrance.width * 0.32, entrance.width * 0.32) + formation_x
        spawn_jitter_y = self.rng.uniform(-entrance.height * 0.30, entrance.height * 0.30) + formation_y
        target_jitter_x = self.rng.uniform(8.0, max(18.0, entrance.width * 0.22))
        target_jitter_y = self.rng.uniform(-entrance.height * 0.28, entrance.height * 0.28)
        doorway_max_x = entrance.x + max(18.0, entrance.width * 0.22)
        student = Student(
            id=self.next_student_id,
            meat_pref=meat_pref,
            veg_pref=veg_pref,
            appetite=self.rng.uniform(0.8, 1.8),
            eat_speed=self.rng.uniform(0.028, 0.075),
            hesitation_time=self.rng.uniform(10.0, 28.0),
            table_walk_time=self.rng.uniform(35.0, 70.0),
            spawn_time=self.game_time,
            x=max(64.0, min(doorway_max_x, entrance.x + spawn_jitter_x)),
            y=max(28.0, min(self.height - 28.0, entrance.y + spawn_jitter_y)),
            target_x=max(64.0, min(self.width - 64.0, entrance.x + target_jitter_x)),
            target_y=max(28.0, min(self.height - 28.0, entrance.y + target_jitter_y)),
            walk_speed=self.rng.uniform(8.0, 14.0),
            preferences=preferences,
            group_id=group_id,
            group_size=group_size,
            entrance_id=entrance.id,
        )
        student.decision_done_at = self.game_time + student.hesitation_time
        return student

    def _register_student(
        self,
        student: Student,
        dish_id: int | None,
        stall_id: int | None,
    ) -> None:
        student.dish_id = dish_id
        student.stall_id = stall_id
        self.students[student.id] = student
        self.next_student_id += 1
        self.spawned_students += 1
        if student.entrance_id is not None:
            self.entrance_flow_counts[student.entrance_id] = (
                self.entrance_flow_counts.get(student.entrance_id, 0) + 1
            )
            self.data_recorder.record_event(
                EventRecordP0(
                    event_type="entrance_used",
                    game_time=self.game_time,
                    student_id=student.id,
                    entrance_id=student.entrance_id,
                )
            )
        if student.group_id is not None:
            self.data_recorder.record_event(
                EventRecordP0(
                    event_type="group_member_joined",
                    game_time=self.game_time,
                    student_id=student.id,
                    group_id=student.group_id,
                    group_size=student.group_size,
                )
            )
        self._record_student_event(
            "student_spawned",
            student,
            from_state=None,
            to_state=student.state,
        )

    def _choose_best_stall(self, student: Student) -> int:
        _, stall_id = self._choose_dish_and_stall(student)
        if stall_id is not None:
            return stall_id
        return min(self.stalls, key=lambda stall: len(stall.queue)).id

    def _choose_dish_and_stall(self, student: Student) -> tuple[int | None, int | None]:
        best_dish_id: int | None = None
        best_dish_score: float | None = None
        seen_dishes: set[int] = set()
        for stall in self.stalls:
            for dish in stall.dishes:
                if dish.id in seen_dishes or not self._dish_has_order_capacity(stall, dish):
                    continue
                seen_dishes.add(dish.id)
                score = self._dish_preference_cost(student, dish)
                if best_dish_score is None or score < best_dish_score:
                    best_dish_score = score
                    best_dish_id = dish.id

        if best_dish_id is None:
            return None, None

        candidates = [
            (stall, self._dish_by_id(stall, best_dish_id))
            for stall in self.stalls
            if self._dish_by_id(stall, best_dish_id) is not None
        ]
        available = [
            (stall, dish)
            for stall, dish in candidates
            if dish is not None and self._dish_has_order_capacity(stall, dish)
        ]
        if not available:
            return self._choose_dish_and_stall_without(student, excluded_dish_id=best_dish_id)

        best_stall = min(
            available,
            key=lambda item: self._stall_choice_cost(student, item[0], item[1]),
        )[0]
        return best_dish_id, best_stall.id

    def _choose_dish_and_stall_without(
        self,
        student: Student,
        excluded_dish_id: int,
    ) -> tuple[int | None, int | None]:
        best: tuple[float, int, int] | None = None
        for stall in self.stalls:
            for dish in stall.dishes:
                if dish.id == excluded_dish_id or not self._dish_has_order_capacity(stall, dish):
                    continue
                score = self._dish_preference_cost(student, dish) + self._stall_choice_cost(student, stall, dish)
                if best is None or score < best[0]:
                    best = (score, dish.id, stall.id)
        if best is None:
            return None, None
        return best[1], best[2]

    def _dish_preference_cost(self, student: Student, dish: Dish) -> float:
        preferences = student.preferences or {"meat": student.meat_pref, "veg": student.veg_pref}
        taste_cost = 0.0
        for key in ("meat", "veg", "spicy"):
            taste_cost += abs(preferences.get(key, 0.0) - dish.features.get(key, 0.0))
        price_cost = dish.price * preferences.get("price_sensitivity", 0.5) * 0.08
        return taste_cost + price_cost + self.rng.uniform(0.0, 0.08)

    def _stall_choice_cost(self, student: Student, stall: Stall, dish: Dish) -> float:
        wait_tolerance = max(0.1, student.preferences.get("wait_tolerance", 0.5))
        queue_cost = len(stall.queue) * (1.1 - wait_tolerance) * 0.75
        travel_cost = distance(student.x, student.y, stall.x, self.queue_walkway_y) * 0.004
        corridor_x = (student.x + stall.x) / 2.0
        corridor_y = (student.y + self.queue_walkway_y) / 2.0
        corridor_density = self._density_near(corridor_x, corridor_y, 120.0)
        congestion_cost = self._density_near(stall.x, stall.y + 110.0, 105.0) * 0.35
        cook_cost = dish.cook_time * 0.015
        price_cost = dish.price * student.preferences.get("price_sensitivity", 0.5) * 0.04
        return (
            queue_cost
            + travel_cost
            + congestion_cost
            + corridor_density * 0.28
            + cook_cost
            + price_cost
            + self.rng.uniform(0.0, 0.12)
        )

    def _dish_by_id(self, stall: Stall, dish_id: int | None) -> Dish | None:
        if dish_id is None:
            return None
        for dish in stall.dishes:
            if dish.id == dish_id:
                return dish
        return None

    def _dish_has_order_capacity(self, stall: Stall, dish: Dish) -> bool:
        pending_count = sum(
            1
            for order in stall.orders
            if order.dish_id == dish.id and order.status in (OrderStatus.QUEUED, OrderStatus.COOKING)
        )
        return dish.stock - pending_count > 0

    def _complete_ready_food(self) -> None:
        for stall in self.stalls:
            while stall.ready_times and stall.ready_times[0][1] <= self.game_time:
                student_id, ready_at, order_id = stall.ready_times.pop(0)
                if stall.queue and stall.queue[0] == student_id:
                    stall.queue.pop(0)
                elif student_id in stall.queue:
                    stall.queue.remove(student_id)

                student = self.students.get(student_id)
                if student is None or student.state == StudentState.DONE:
                    continue
                order = self._order_by_id(stall, order_id)
                if order is not None:
                    order.status = OrderStatus.DONE
                    order.finished_at = ready_at
                dish = self._dish_by_id(stall, student.dish_id)
                stock_before = dish.stock if dish is not None else None
                if dish is not None and dish.stock > 0:
                    dish.stock -= 1
                    self.data_recorder.record_event(
                        EventRecordP0(
                            event_type="dish_stock_changed",
                            game_time=ready_at,
                            student_id=student.id,
                            stall_id=stall.id,
                            dish_id=dish.id,
                            order_id=order_id,
                            stock_before=stock_before,
                            stock_after=dish.stock,
                        )
                    )
                    if dish.stock == 0:
                        self.data_recorder.record_event(
                            EventRecordP0(
                                event_type="dish_sold_out",
                                game_time=ready_at,
                                stall_id=stall.id,
                                dish_id=dish.id,
                                stock_before=stock_before,
                                stock_after=dish.stock,
                            )
                        )
                if order is not None:
                    self.data_recorder.record_event(
                        EventRecordP0(
                            event_type="order_completed",
                            game_time=ready_at,
                            student_id=student.id,
                            stall_id=stall.id,
                            dish_id=order.dish_id,
                            order_id=order.id,
                            price=dish.price if dish is not None else None,
                            quantity=1,
                            stock_before=stock_before,
                            stock_after=dish.stock if dish is not None else None,
                            order_status=OrderStatus.DONE.value,
                            stall_status=stall.status.value if isinstance(stall.status, StallStatus) else str(stall.status),
                        )
                    )
                stall.refresh_status()
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
                    if not self._student_has_occupied_seat(student):
                        self.issues.append(f"student {student.id} reached seat without a valid occupied reservation")
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
                    self.finished_eating_students += 1
            elif student.state == StudentState.MOVING_TO_TRAY_RETURN:
                arrived = self._move_student(student, game_delta, student.walk_speed)
                if arrived or self._is_inside_tray_return(student):
                    self._record_student_event(
                        "tray_return_reached",
                        student,
                        from_state=student.state,
                        to_state=StudentState.LEAVING,
                    )
                    self._set_exit_path(student)
                    student.state = StudentState.LEAVING
            elif student.state == StudentState.LEAVING:
                arrived = self._move_student(student, game_delta, student.walk_speed * 0.95)
                if arrived or self._is_inside_exit(student):
                    previous_state = student.state
                    student.state = StudentState.DONE
                    if student.exit_id is not None:
                        self.exit_flow_counts[student.exit_id] = (
                            self.exit_flow_counts.get(student.exit_id, 0) + 1
                        )
                        self.data_recorder.record_event(
                            EventRecordP0(
                                event_type="exit_used",
                                game_time=self.game_time,
                                student_id=student.id,
                                exit_id=student.exit_id,
                            )
                        )
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
            entrance = self._entrance_for_student(student)
            student.target_x = entrance.x + self.rng.uniform(8.0, max(18.0, entrance.width * 0.22))
            student.target_y = entrance.y + self.rng.uniform(-entrance.height * 0.30, entrance.height * 0.30)
            student.target_x = max(28.0, min(self.width - 28.0, student.target_x))
            student.target_y = max(28.0, min(self.height - 28.0, student.target_y))
        self._move_student(student, game_delta, student.walk_speed * 0.2)

    def _entrance_for_student(self, student: Student) -> Entrance:
        if student.entrance_id is not None:
            for entrance in self.entrances:
                if entrance.id == student.entrance_id:
                    return entrance
        return self.entrances[0]

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
        self._set_navigation_path(student, target)

    def _queue_approach_y(self, student: Student) -> float:
        if student.y >= 470.0:
            return self.bottom_walkway_y
        if student.y >= 240.0:
            return self.top_walkway_y
        return self.queue_walkway_y

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
            student.dish_id, student.stall_id = self._choose_dish_and_stall(student)
        if student.stall_id is None:
            self._send_student_to_exit(student, reason="no_available_stall")
            return
        stall = self.stalls[student.stall_id]
        dish = self._dish_by_id(stall, student.dish_id)
        if dish is None or not self._dish_has_order_capacity(stall, dish):
            student.dish_id, student.stall_id = self._choose_dish_and_stall(student)
            if student.stall_id is None:
                self._send_student_to_exit(student, reason="no_available_dish")
                return
            stall = self.stalls[student.stall_id]
            dish = self._dish_by_id(stall, student.dish_id)
            if dish is None or not self._dish_has_order_capacity(stall, dish):
                self._send_student_to_exit(student, reason="no_order_capacity")
                return
        if student.id in stall.queue:
            student.state = StudentState.QUEUED
            return
        started_at = max(self.game_time, stall.next_food_ready_time)
        ready_at = started_at + dish.cook_time
        order = Order(
            id=self.next_order_id,
            student_id=student.id,
            stall_id=stall.id,
            dish_id=dish.id,
            created_at=self.game_time,
            started_at=started_at,
            finished_at=ready_at,
            status=OrderStatus.COOKING if started_at <= self.game_time else OrderStatus.QUEUED,
        )
        self.next_order_id += 1
        stall.orders.append(order)
        stall.next_food_ready_time = ready_at
        stall.queue.append(student.id)
        stall.ready_times.append((student.id, ready_at, order.id))
        student.order_id = order.id
        self.data_recorder.record_event(
            EventRecordP0(
                event_type="order_created",
                game_time=self.game_time,
                student_id=student.id,
                stall_id=stall.id,
                dish_id=dish.id,
                order_id=order.id,
                price=dish.price,
                quantity=1,
                order_status=order.status.value,
                stall_status=stall.status.value if isinstance(stall.status, StallStatus) else str(stall.status),
            )
        )
        if order.status == OrderStatus.COOKING:
            self.data_recorder.record_event(
                EventRecordP0(
                    event_type="order_started",
                    game_time=self.game_time,
                    student_id=student.id,
                    stall_id=stall.id,
                    dish_id=dish.id,
                    order_id=order.id,
                    order_status=order.status.value,
                    stall_status=stall.status.value if isinstance(stall.status, StallStatus) else str(stall.status),
                )
            )
        previous_state = student.state
        student.state = StudentState.QUEUED
        self._record_student_event(
            "queue_started",
            student,
            from_state=previous_state,
            to_state=student.state,
        )

    def _order_by_id(self, stall: Stall, order_id: int) -> Order | None:
        for order in stall.orders:
            if order.id == order_id:
                return order
        return None

    def _refresh_orders_and_stalls(self) -> None:
        for stall in self.stalls:
            for order in stall.orders:
                if order.status != OrderStatus.QUEUED:
                    continue
                if order.started_at is not None and self.game_time >= order.started_at:
                    order.status = OrderStatus.COOKING
                    self.data_recorder.record_event(
                        EventRecordP0(
                            event_type="order_started",
                            game_time=order.started_at,
                            student_id=order.student_id,
                            stall_id=order.stall_id,
                            dish_id=order.dish_id,
                            order_id=order.id,
                            order_status=order.status.value,
                            stall_status=stall.status.value if isinstance(stall.status, StallStatus) else str(stall.status),
                        )
                    )
            stall.refresh_status()

    def _send_student_to_table(self, student: Student) -> None:
        free: list[tuple[Table, int]] = []
        for table in self.tables:
            for seat_index in table.free_seat_indexes():
                free.append((table, seat_index))
        if not free:
            if student.waiting_seat_since is None:
                student.waiting_seat_since = self.game_time
            if self.game_time - student.waiting_seat_since >= MAX_SEAT_WAIT_SECONDS:
                self._send_student_to_exit(student, reason="seat_wait_timeout")
                return
            if student.state != StudentState.WAITING_SEAT:
                student.state = StudentState.WAITING_SEAT
                self._set_navigation_path(student, (self.width - 70.0, self.top_walkway_y))
                return
            student.state = StudentState.WAITING_SEAT
            return

        student.waiting_seat_since = None
        table, seat_index, path, walk_distance = self._best_seat_candidate(student, free)
        seat = table.seats[seat_index]
        seat.status = SeatStatus.RESERVED
        seat.student_id = student.id
        student.table_id = table.id
        student.seat_index = seat_index
        self._set_path(student, path)
        self._start_path_tracking(
            student,
            path,
            start=(student.x, student.y),
            kind="seat",
        )
        student.table_walk_speed = max(6.0, walk_distance / student.table_walk_time)
        student.state = StudentState.MOVING_TO_SEAT
        self.data_recorder.record_event(
            EventRecordP0(
                event_type="seat_assigned",
                game_time=self.game_time,
                student_id=student.id,
                group_id=student.group_id,
                group_size=student.group_size,
                table_id=table.id,
                seat_index=seat_index,
                table_type=table.table_type,
                seat_count=table.seat_count,
            )
        )

    def _best_seat_candidate(
        self,
        student: Student,
        free: list[tuple[Table, int]],
    ) -> tuple[Table, int, list[tuple[float, float]], float]:
        best: tuple[float, Table, int, float, float] | None = None
        for table, seat_index in free:
            seat_x, seat_y = self._seat_position(table, seat_index)
            estimated_walk_distance = self._estimated_walk_distance(student.x, student.y, seat_x, seat_y)
            table_density = self._density_near(table.x, table.y, 92.0)
            tray_distance = distance(seat_x, seat_y, *self._nearest_tray_return_center(seat_x, seat_y))
            occupied_bias = table.occupied_count * 18.0
            group_bias = self._group_seat_bias(student, table, seat_index)
            jitter = self.rng.uniform(0.0, 6.0)
            score = (
                estimated_walk_distance
                + table_density * 55.0
                + tray_distance * 0.08
                + occupied_bias
                + group_bias
                + jitter
            )
            if best is None or score < best[0]:
                best = (score, table, seat_index, seat_x, seat_y)
        assert best is not None
        _, table, seat_index, seat_x, seat_y = best
        path = self._build_table_path(student.x, student.y, table, seat_index, seat_x, seat_y)
        walk_distance = self._path_distance(student.x, student.y, path)
        return table, seat_index, path, walk_distance

    def _estimated_walk_distance(self, start_x: float, start_y: float, target_x: float, target_y: float) -> float:
        return manhattan_2d(start_x, start_y, target_x, target_y) * 1.08

    def _group_seat_bias(self, student: Student, table: Table, seat_index: int) -> float:
        if student.group_id is None:
            return 0.0

        group_members = [
            member
            for member in self.students.values()
            if member.id != student.id
            and member.group_id == student.group_id
            and member.table_id is not None
            and member.seat_index is not None
        ]
        if not group_members:
            if table.free_seat_indexes() and len(table.free_seat_indexes()) >= max(1, student.group_size or 1):
                return -20.0
            return 0.0

        same_table_members = [member for member in group_members if member.table_id == table.id]
        if same_table_members:
            distance_to_group = min(
                self._seat_adjacency_distance(table, seat_index, member.seat_index)
                for member in same_table_members
                if member.seat_index is not None
            )
            return -260.0 - 35.0 / max(1, distance_to_group)

        nearest_group_table_distance = min(
            distance(table.x, table.y, self.tables[member.table_id].x, self.tables[member.table_id].y)
            for member in group_members
            if member.table_id is not None
        )
        return min(120.0, nearest_group_table_distance * 0.25)

    def _seat_adjacency_distance(self, table: Table, first_index: int, second_index: int) -> float:
        first_x, first_y = self._seat_position(table, first_index)
        second_x, second_y = self._seat_position(table, second_index)
        return max(1.0, distance(first_x, first_y, second_x, second_y))

    def _occupy_reserved_seat(self, student: Student) -> None:
        if student.table_id is None or student.seat_index is None:
            return
        seat = self.tables[student.table_id].seats[student.seat_index]
        if seat.student_id == student.id and seat.status == SeatStatus.RESERVED:
            seat.status = SeatStatus.OCCUPIED

    def _student_has_occupied_seat(self, student: Student) -> bool:
        if student.table_id is None or student.seat_index is None:
            return False
        seat = self.tables[student.table_id].seats[student.seat_index]
        return seat.student_id == student.id and seat.status == SeatStatus.OCCUPIED

    def _release_seat(self, student: Student) -> None:
        if student.table_id is None or student.seat_index is None:
            return
        table = self.tables[student.table_id]
        seat = table.seats[student.seat_index]
        if seat.student_id == student.id:
            seat.status = SeatStatus.FREE
            seat.student_id = None
            self.data_recorder.record_event(
                EventRecordP0(
                    event_type="seat_released",
                    game_time=self.game_time,
                    student_id=student.id,
                    group_id=student.group_id,
                    group_size=student.group_size,
                    table_id=table.id,
                    seat_index=student.seat_index,
                    table_type=table.table_type,
                    seat_count=table.seat_count,
                )
            )
        student.table_id = None
        student.seat_index = None

    def _seat_position(self, table: Table, seat_index: int) -> tuple[float, float]:
        offsets = self._seat_offsets(table.seat_count)
        dx, dy = offsets[min(seat_index, len(offsets) - 1)]
        return table.x + dx, table.y + dy

    def _seat_offsets(self, seat_count: int) -> list[tuple[float, float]]:
        if seat_count <= 2:
            return [(-50.0, 0.0), (50.0, 0.0)]
        if seat_count <= 4:
            return [(-50.0, -42.0), (50.0, -42.0), (-50.0, 42.0), (50.0, 42.0)]
        return [
            (-54.0, -50.0),
            (54.0, -50.0),
            (-54.0, 0.0),
            (54.0, 0.0),
            (-54.0, 50.0),
            (54.0, 50.0),
        ][:seat_count]

    def _build_table_path(
        self,
        start_x: float,
        start_y: float,
        table: Table,
        seat_index: int,
        seat_x: float,
        seat_y: float,
    ) -> list[tuple[float, float]]:
        return self._build_navigation_path((start_x, start_y), (seat_x, seat_y))

    def _set_exit_path(self, student: Student) -> None:
        exit_area = self._choose_exit(student)
        student.exit_id = exit_area.id
        exit_point = (exit_area.x, exit_area.y)
        self._set_navigation_path(student, exit_point)

    def _send_student_to_exit(self, student: Student, reason: str) -> None:
        self.issues.append(f"student {student.id} leaving early: {reason}")
        if student.order_id is not None and student.stall_id is not None:
            stall = self.stalls[student.stall_id]
            order = self._order_by_id(stall, student.order_id)
            if order is not None and order.status in (OrderStatus.QUEUED, OrderStatus.COOKING):
                order.status = OrderStatus.CANCELLED
                self.data_recorder.record_event(
                    EventRecordP0(
                        event_type="order_cancelled",
                        game_time=self.game_time,
                        student_id=student.id,
                        stall_id=stall.id,
                        dish_id=order.dish_id,
                        order_id=order.id,
                        order_status=order.status.value,
                    )
                )
        self._release_seat(student)
        previous_state = student.state
        self._set_exit_path(student)
        student.state = StudentState.LEAVING
        self._record_student_event(
            "early_leave_started",
            student,
            from_state=previous_state,
            to_state=student.state,
        )

    def _choose_exit(self, student: Student) -> Exit:
        if student.exit_id is not None:
            for exit_area in self.exits:
                if exit_area.id == student.exit_id:
                    return exit_area
        return min(
            self.exits,
            key=lambda exit_area: (
                distance(student.x, student.y, exit_area.x, exit_area.y)
                + self._exit_density(exit_area) * 90.0
            ),
        )

    def _exit_density(self, exit_area: Exit) -> int:
        return sum(
            1
            for student in self.students.values()
            if student.state == StudentState.LEAVING
            and student.exit_id == exit_area.id
            and distance(student.x, student.y, exit_area.x, exit_area.y) <= 140.0
        )

    def _set_tray_return_path(self, student: Student) -> None:
        point = self._nearest_tray_return_center(student.x, student.y)
        self._set_navigation_path(student, point)

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
        seat_x, _ = self._seat_position(table, seat_index)
        if seat_x < table.x:
            return max(92.0, table.x - 92.5 if column > 0 else 92.0)
        return min(self.width - 64.0, table.x + 92.5)

    def _seat_access_y(self, table: Table, seat_index: int) -> float:
        _, seat_y = self._seat_position(table, seat_index)
        if seat_y < table.y:
            return max(self.top_walkway_y, table.y - 56.0)
        return min(self.height - 64.0, table.y + 56.0)

    def _set_navigation_path(self, student: Student, target: tuple[float, float]) -> None:
        start = (student.x, student.y)
        path = self._build_navigation_path(
            start,
            target,
            ignored_student_id=student.id,
        )
        self._set_path(student, path)
        self._start_path_tracking(student, path, start=start, kind=student.state.value)

    def _build_navigation_path(
        self,
        start: tuple[float, float],
        target: tuple[float, float],
        ignored_student_id: int | None = None,
    ) -> list[tuple[float, float]]:
        pathfinder = self._navigation_pathfinder()
        pathfinder.set_congestion_points(self._navigation_congestion_points(ignored_student_id))
        foot_start = self._foot_point_from_position(start[0], start[1])
        foot_target = self._foot_point_from_position(target[0], target[1])
        foot_path = pathfinder.find_path(foot_start, foot_target)
        return self._compact_path([(x, y - 14.0) for x, y in foot_path])

    def _navigation_pathfinder(self) -> GridPathFinder:
        if self._navigation_pathfinder_cache is None:
            self._navigation_pathfinder_cache = GridPathFinder(
                width=float(self.width),
                height=float(self.height),
                obstacles=self._navigation_obstacles(),
                doorways=self._navigation_doorways(),
            )
        return self._navigation_pathfinder_cache

    def _navigation_obstacles(self) -> list[NavRect]:
        if self._navigation_obstacle_cache is None:
            self._navigation_obstacle_cache = [
                NavRect(
                    left=float(item["left"]),
                    top=float(item["top"]),
                    right=float(item["right"]),
                    bottom=float(item["bottom"]),
                    kind=str(item["kind"]),
                )
                for item in self._obstacle_frames()
            ]
        return self._navigation_obstacle_cache

    def _navigation_doorways(self) -> list[Doorway]:
        if self._navigation_doorway_cache is None:
            doorways = [
                Doorway(entrance.x, entrance.y, entrance.width, entrance.height, "left")
                for entrance in self.entrances
            ]
            doorways.extend(
                Doorway(exit_area.x, exit_area.y, exit_area.width, exit_area.height, "right")
                for exit_area in self.exits
            )
            self._navigation_doorway_cache = doorways
        return self._navigation_doorway_cache

    def _navigation_congestion_points(self, ignored_student_id: int | None = None) -> list[tuple[float, float]]:
        return [
            self._student_foot_point(student)
            for student in self.students.values()
            if student.id != ignored_student_id
            and student.state not in (StudentState.QUEUED, StudentState.EATING, StudentState.DONE)
        ]

    def _set_path(self, student: Student, path: list[tuple[float, float]]) -> None:
        student.path = self._compact_path(path)
        if student.path:
            student.target_x, student.target_y = student.path[0]

    def _start_path_tracking(
        self,
        student: Student,
        path: list[tuple[float, float]],
        start: tuple[float, float],
        kind: str,
    ) -> None:
        student.path_id = f"s{student.id}-p{self.next_path_id}"
        self.next_path_id += 1
        student.path_started_at = self.game_time
        student.path_length = self._path_distance(start[0], start[1], path)
        self.data_recorder.record_event(
            EventRecordP0(
                event_type="path_planned",
                game_time=self.game_time,
                student_id=student.id,
                path_id=student.path_id,
                path_length=student.path_length,
                path_blocked=not bool(path),
                from_state=kind,
            )
        )

    def _complete_path_tracking(self, student: Student) -> None:
        if student.path_id is None:
            return
        self.data_recorder.record_event(
            EventRecordP0(
                event_type="path_completed",
                game_time=self.game_time,
                student_id=student.id,
                path_id=student.path_id,
                path_length=student.path_length,
                path_duration=(
                    self.game_time - student.path_started_at
                    if student.path_started_at is not None
                    else None
                ),
            )
        )
        student.path_id = None
        student.path_started_at = None
        student.path_length = None

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
        step_distance = speed * game_delta
        arrival_radius = 3.0 if not student.path else 5.5
        if target_distance <= max(arrival_radius, step_distance):
            student.x, student.y = student.target_x, student.target_y
            arrived = True
        else:
            next_x, next_y, arrived = move_towards(
                student.x,
                student.y,
                student.target_x,
                student.target_y,
                step_distance,
            )
            if self._is_static_walkable_point(next_x, next_y):
                student.x = next_x
                student.y = next_y
            elif self._reroute_student(student):
                arrived = False
            else:
                arrived = False
            student.x = max(28.0, min(self.width - 28.0, student.x))
            student.y = max(28.0, min(self.height - 28.0, student.y))
            arrived = arrived or distance(student.x, student.y, student.target_x, student.target_y) <= arrival_radius

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
        if arrived:
            self._complete_path_tracking(student)
        return arrived

    def _separate_students(self, game_delta: float) -> None:
        movable = [
            student
            for student in self.students.values()
            if student.state not in (StudentState.EATING, StudentState.DONE)
        ]
        congestion_distance = 34.0
        crowded_ids: set[int] = set()
        for index, first in enumerate(movable):
            for second in movable[index + 1 :]:
                first_foot_x, first_foot_y = self._student_foot_point(first)
                second_foot_x, second_foot_y = self._student_foot_point(second)
                if distance(first_foot_x, first_foot_y, second_foot_x, second_foot_y) < congestion_distance:
                    crowded_ids.add(first.id)
                    crowded_ids.add(second.id)

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
        return [
            (item["left"], item["top"], item["right"], item["bottom"])
            for item in self._obstacle_frames()
        ]

    def _obstacle_frames(self) -> list[dict[str, Any]]:
        rects: list[dict[str, Any]] = []
        for stall in self.stalls:
            rects.append(
                {
                    "left": stall.x - 66.0,
                    "top": stall.y - 52.0,
                    "right": stall.x + 66.0,
                    "bottom": stall.y + 62.0,
                    "kind": "stall",
                }
            )
        for table in self.tables:
            rects.append(
                {
                    "left": table.x - 48.0,
                    "top": table.y - 22.0,
                    "right": table.x + 48.0,
                    "bottom": table.y + 22.0,
                    "kind": "table",
                }
            )
        rects.extend(
            [
                {"left": 34.0, "top": 34.0, "right": self.width - 34.0, "bottom": 44.0, "kind": "wall"},
                {"left": 34.0, "top": 34.0, "right": 44.0, "bottom": self.height - 34.0, "kind": "wall"},
                {"left": self.width - 44.0, "top": 34.0, "right": self.width - 34.0, "bottom": self.height - 34.0, "kind": "wall"},
            ]
        )
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

    def _is_static_walkable_point(self, x: float, y: float) -> bool:
        margin = 30.0
        foot_x, foot_y = self._foot_point_from_position(x, y)
        if foot_x < margin or foot_x > self.width - margin or foot_y < margin or foot_y > self.height - margin:
            return False
        for item in self._obstacle_frames():
            if item["kind"] == "wall" and self._is_doorway_point(foot_x, foot_y):
                continue
            if item["left"] - 14.0 <= foot_x <= item["right"] + 14.0 and item["top"] - 14.0 <= foot_y <= item["bottom"] + 14.0:
                return False
        return True

    def _is_doorway_point(self, foot_x: float, foot_y: float) -> bool:
        for entrance in self.entrances:
            if foot_x <= entrance.x + 36.0 and abs(foot_y - entrance.y) <= entrance.height * 0.62:
                return True
        for exit_area in self.exits:
            if foot_x >= exit_area.x - 36.0 and abs(foot_y - exit_area.y) <= exit_area.height * 0.62:
                return True
        return False

    def _is_inside_exit(self, student: Student) -> bool:
        exit_area = self._choose_exit(student)
        left, top, right, bottom = self._exit_rect(exit_area)
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

    def _exit_rect(self, exit_area: Exit) -> tuple[float, float, float, float]:
        half_width = exit_area.width / 2.0
        half_height = exit_area.height / 2.0
        return (
            exit_area.x - half_width,
            exit_area.y - half_height,
            exit_area.x + half_width,
            exit_area.y + half_height,
        )

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
        for student in moving:
            if student.path_id is None:
                continue
            self.data_recorder.record_event(
                EventRecordP0(
                    event_type="path_congestion_sample",
                    game_time=self.game_time,
                    student_id=student.id,
                    path_id=student.path_id,
                    path_congestion_index=max(0.0, min(1.0, student.stuck_time / 10.0)),
                )
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
        stats = self.data_recorder.build_stats(current_time=self.game_time).to_dict()
        issues = [*self.issues, *self.data_recorder.issues]
        frame = {
            "game_time": min(self.game_time, self.config.duration_game_seconds),
            "duration": self.config.duration_game_seconds,
            "time_scale": self.time_scale,
            "spawned_students": self.spawned_students,
            "finished_eating_students": self.finished_eating_students,
            "served_students": self.finished_eating_students,
            "active_students": self._active_student_count(),
            "issues": issues,
            "door": self.door,
            "exit": self.exit,
            "entrances": [self._entrance_frame(entrance) for entrance in self.entrances],
            "exits": [self._exit_frame(exit_area) for exit_area in self.exits],
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
            "path_debug_lines": self._build_walk_paths(),
            "obstacles": self._obstacle_frames(),
            "collision_boxes": self._build_collision_boxes(),
            "stalls": [self._stall_frame(stall) for stall in self.stalls],
            "tables": [
                {
                    "id": table.id,
                    "x": table.x,
                    "y": table.y,
                    "table_type": table.table_type,
                    "seat_count": table.seat_count,
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
                self._student_frame(student)
                for student in self.students.values()
                if student.state != StudentState.DONE
            ],
        }
        return frame

    def _entrance_frame(self, entrance: Entrance) -> dict[str, Any]:
        return {
            "id": entrance.id,
            "x": entrance.x,
            "y": entrance.y,
            "width": entrance.width,
            "height": entrance.height,
            "weight": entrance.weight,
        }

    def _exit_frame(self, exit_area: Exit) -> dict[str, Any]:
        return {
            "id": exit_area.id,
            "x": exit_area.x,
            "y": exit_area.y,
            "width": exit_area.width,
            "height": exit_area.height,
            "is_congested": self._exit_density(exit_area) >= 4,
        }


    def _stall_frame(self, stall: Stall) -> dict[str, Any]:
        dishes = stall.dishes or []
        orders = stall.orders or []
        queue_count = len(stall.queue or [])
        return {
            "id": stall.id,
            "x": stall.x,
            "y": stall.y,
            "meat_ratio": stall.meat_ratio,
            "veg_ratio": stall.veg_ratio,
            "cook_time": stall.cook_time,
            "cook_remaining": self._stall_cook_remaining(stall),
            "cook_progress": self._stall_cook_progress(stall),
            "queue_count": queue_count,
            "status": stall.status.value if isinstance(stall.status, StallStatus) else str(stall.status),
            "is_congested": queue_count >= 8,
            "dishes": [self._dish_frame(dish) for dish in dishes],
            "orders": [self._order_frame(order) for order in orders],
        }

    def _dish_frame(self, dish: Dish) -> dict[str, Any]:
        return {
            "id": dish.id,
            "name": dish.name or "",
            "features": dict(dish.features or {}),
            "price": round(float(dish.price), 2),
            "stock": max(0, int(dish.stock)),
            "cook_time": float(dish.cook_time),
            "available": bool(dish.available),
        }

    def _order_frame(self, order: Order) -> dict[str, Any]:
        status = order.status.value if isinstance(order.status, OrderStatus) else str(order.status)
        return {
            "id": order.id,
            "student_id": order.student_id,
            "stall_id": order.stall_id,
            "dish_id": order.dish_id,
            "created_at": float(order.created_at),
            "started_at": order.started_at,
            "finished_at": order.finished_at if status == OrderStatus.DONE.value else None,
            "status": status,
        }

    def _student_frame(self, student: Student) -> dict[str, Any]:
        return {
            "id": student.id,
            "x": student.x,
            "y": student.y,
            "target_x": student.target_x,
            "target_y": student.target_y,
            "path": list(student.path or []),
            "state": student.state.value if isinstance(student.state, StudentState) else str(student.state),
            "meat_pref": student.meat_pref,
            "veg_pref": student.veg_pref,
            "preferences": dict(student.preferences or {}),
            "dish_id": student.dish_id,
            "order_id": student.order_id,
            "group_id": student.group_id,
            "group_size": student.group_size,
            "entrance_id": student.entrance_id,
            "exit_id": student.exit_id,
            "stall_id": student.stall_id,
            "table_id": student.table_id,
            "seat_index": student.seat_index,
            "actual_speed": student.actual_speed,
            "stuck_time": student.stuck_time,
            "reroute_count": student.reroute_count,
            "facing_x": student.facing_x,
            "facing_y": student.facing_y,
        }

    def _stall_cook_remaining(self, stall: Stall) -> float:
        if not stall.ready_times:
            return 0.0
        return max(0.0, stall.ready_times[0][1] - self.game_time)

    def _stall_cook_progress(self, stall: Stall) -> float:
        if not stall.ready_times:
            return 0.0
        _, _, order_id = stall.ready_times[0]
        order = self._order_by_id(stall, order_id)
        dish = self._dish_by_id(stall, order.dish_id) if order is not None else None
        cook_time = dish.cook_time if dish is not None else stall.cook_time
        if cook_time <= 0:
            return 0.0
        remaining = self._stall_cook_remaining(stall)
        return max(0.0, min(1.0, 1.0 - remaining / cook_time))

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
        ]
        for exit_area in self.exits:
            paths.append(
                {
                    "kind": "exit",
                    "points": [
                        (self.width - 155.0, exit_area.y),
                        (exit_area.x, exit_area.y),
                    ],
                }
            )
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


def _load_menu_config(path: Path) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    fallback = _default_menu_config()
    try:
        with path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
    except OSError as exc:
        return fallback, [f"menu config not loaded: {exc}"]
    except json.JSONDecodeError as exc:
        return fallback, [f"menu config invalid json: {exc}"]

    try:
        dishes = raw["dishes"]
        if not isinstance(dishes, list) or not dishes:
            raise ValueError("dishes must be a non-empty list")
        normalized_dishes: list[dict[str, Any]] = []
        for index, dish in enumerate(dishes):
            if not isinstance(dish, dict):
                raise ValueError(f"dish {index} must be an object")
            features = dish.get("features")
            if not isinstance(features, dict):
                raise ValueError(f"dish {index} missing features")
            normalized_dishes.append(
                {
                    "id": int(dish["id"]),
                    "name": str(dish["name"]),
                    "features": {str(key): float(value) for key, value in features.items()},
                    "price": float(dish["price"]),
                    "stock": max(0, int(dish["stock"])),
                    "cook_time": max(1.0, float(dish["cook_time"])),
                }
            )
        return {
            "dishes_per_stall": max(1, int(raw.get("dishes_per_stall", 3))),
            "price_jitter": _two_float_tuple(raw.get("price_jitter"), (-0.5, 0.8)),
            "cook_time_jitter": _two_float_tuple(raw.get("cook_time_jitter"), (-2.0, 3.0)),
            "dishes": normalized_dishes,
        }, issues
    except (KeyError, TypeError, ValueError) as exc:
        return fallback, [f"menu config invalid schema: {exc}"]


def _two_float_tuple(value: Any, default: tuple[float, float]) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return default
    first = float(value[0])
    second = float(value[1])
    return min(first, second), max(first, second)


def _default_menu_config() -> dict[str, Any]:
    return {
        "dishes_per_stall": 3,
        "price_jitter": (-0.5, 0.8),
        "cook_time_jitter": (-2.0, 3.0),
        "dishes": [
            {"id": 1, "name": "Braised Chicken Rice", "features": {"meat": 0.88, "veg": 0.22, "spicy": 0.35}, "price": 13.0, "stock": 24, "cook_time": 22.0},
            {"id": 2, "name": "Tomato Egg Noodles", "features": {"meat": 0.18, "veg": 0.72, "spicy": 0.05}, "price": 9.5, "stock": 24, "cook_time": 16.0},
            {"id": 3, "name": "Beef Noodles", "features": {"meat": 0.78, "veg": 0.34, "spicy": 0.42}, "price": 15.0, "stock": 24, "cook_time": 24.0},
            {"id": 4, "name": "Vegetable Set Meal", "features": {"meat": 0.08, "veg": 0.92, "spicy": 0.12}, "price": 10.0, "stock": 24, "cook_time": 18.0},
            {"id": 5, "name": "Spicy Pork Rice", "features": {"meat": 0.72, "veg": 0.38, "spicy": 0.82}, "price": 12.0, "stock": 24, "cook_time": 20.0},
            {"id": 6, "name": "Mushroom Chicken Soup", "features": {"meat": 0.56, "veg": 0.66, "spicy": 0.02}, "price": 11.5, "stock": 24, "cook_time": 19.0},
        ],
    }
