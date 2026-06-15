from __future__ import annotations

import json
import random
from math import hypot
from pathlib import Path
from typing import Any

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
STALL_COOK_TIME_MIN_SECONDS = 1.0 * 60.0
STALL_COOK_TIME_MAX_SECONDS = 3.0 * 60.0
EATING_TIME_MIN_SECONDS = 5.0 * 60.0
EATING_TIME_MAX_SECONDS = 25.0 * 60.0
EATING_TIME_MEAN_SECONDS = (EATING_TIME_MIN_SECONDS + EATING_TIME_MAX_SECONDS) / 2.0
EATING_TIME_STDDEV_SECONDS = (EATING_TIME_MAX_SECONDS - EATING_TIME_MIN_SECONDS) / 6.0
STUDENT_COLLISION_WIDTH = 22.0
STUDENT_COLLISION_HEIGHT = 18.0
STUDENT_COLLISION_FOOT_OFFSET_Y = 14.0
STUDENT_COLLISION_PADDING = 2.0
LOCAL_AVOIDANCE_SIDE_STEP = max(STUDENT_COLLISION_WIDTH, STUDENT_COLLISION_HEIGHT) * 1.5
LOCAL_AVOIDANCE_REACHABILITY_CHECK_COUNT = 2
LOCAL_AVOIDANCE_REROUTE_SECONDS = 3.0
PATH_REUSE_TARGET_TOLERANCE = 8.0
PATH_REPLAN_COOLDOWN_SECONDS = 0.5
QUEUE_TARGET_REPLAN_SHIFT = 18.0
QUEUE_TARGET_REPLAN_NEAR_DISTANCE = 160.0
STUCK_RECOVERY_SECONDS = 30.0
TABLE_OVERLAP_RELOCATION_SECONDS = 60.0
TABLE_SEAT_OFFSETS: dict[int, list[tuple[float, float]]] = {
    2: [(-36.0, 0.0), (36.0, 0.0)],
    4: [(-46.0, -22.0), (46.0, -22.0), (-46.0, 26.0), (46.0, 26.0)],
    6: [(-54.0, -32.0), (54.0, -32.0), (-54.0, 0.0), (54.0, 0.0), (-54.0, 32.0), (54.0, 32.0)],
}
TABLE_OBSTACLE_SIZES: dict[int, tuple[float, float]] = {
    2: (74.0, 56.0),
    4: (88.0, 74.0),
    6: (104.0, 88.0),
}


class SimulationEngine:
    def __init__(self, config: SimulationConfig) -> None:
        self.config = config
        self.time_scale = config.time_scale
        self.rng = random.Random(config.seed)
        self.width = 1280
        self.height = 800
        self.table_columns = 6
        self.queue_walkway_y = 156.0
        self.top_walkway_y = 260.0
        self.bottom_walkway_y = 724.0
        self.door = (58.0, 156.0)
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
        self._navigation_doorway_cache: list[Doorway] | None = None
        self._navigation_pathfinder_cache: GridPathFinder | None = None
        self._walk_paths_cache: list[dict[str, Any]] | None = None
        self._stop_requested = False
        self._paused = False

    def initialize(self) -> None:
        self._initialize()

    def step(
        self,
        game_delta: float,
        *,
        lightweight_students: bool = False,
        include_student_details: bool = False,
    ) -> dict[str, Any]:
        if self.is_finished:
            return self._build_frame(
                lightweight_students=lightweight_students,
                include_student_details=include_student_details,
            )

        game_delta = max(0.0, float(game_delta))
        previous_game_time = self.game_time
        next_game_time = min(self._hard_stop_game_time(), self.game_time + game_delta)
        spawn_cutoff_time = self._student_spawn_cutoff_time()
        if previous_game_time < spawn_cutoff_time < next_game_time:
            self.game_time = spawn_cutoff_time
            self._spawn_due_students()

        self.game_time = next_game_time
        self._spawn_due_students()
        self._complete_ready_food()
        effective_game_delta = self.game_time - previous_game_time
        self._update_students(effective_game_delta)
        self._separate_students(effective_game_delta)
        self._refresh_orders_and_stalls()
        self._record_queue_samples()
        self._record_runtime_sample()
        self.max_active_students_seen = max(
            self.max_active_students_seen,
            self._active_student_count(),
        )
        return self._build_frame(
            lightweight_students=lightweight_students,
            include_student_details=include_student_details,
        )

    def build_frame(
        self,
        *,
        lightweight_students: bool = False,
        include_student_details: bool = False,
    ) -> dict[str, Any]:
        return self._build_frame(
            lightweight_students=lightweight_students,
            include_student_details=include_student_details,
        )

    def summary(self, status: str) -> RunSummary:
        return RunSummary(
            status=status,
            game_time=min(self.game_time, self._hard_stop_game_time()),
            spawned_students=self.spawned_students,
            finished_eating_students=self.finished_eating_students,
            active_students=self._active_student_count(),
        )

    @property
    def is_finished(self) -> bool:
        return self._all_spawned_students_left() or self.game_time >= self._hard_stop_game_time()

    def _hard_stop_game_time(self) -> float:
        return self.config.duration_game_seconds * 1.5

    def _all_spawned_students_left(self) -> bool:
        return self._active_student_count() == 0 and (
            self.spawned_students >= self.config.total_student_count
            or self.game_time >= self._student_spawn_cutoff_time()
        )

    def stop(self) -> None:
        self._stop_requested = True

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

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
        self._navigation_doorway_cache = None
        self._navigation_pathfinder_cache = None
        self._walk_paths_cache = None
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
            (0, 58.0, 156.0, 44.0, 76.0),
            (1, 58.0, 354.0, 44.0, 76.0),
            (2, 58.0, 604.0, 44.0, 76.0),
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
            self.entrances = [Entrance(0, self.door[0], self.door[1], 44.0, 76.0, 1.0)]
        self.door = (self.entrances[0].x, self.entrances[0].y)

    def _build_exits(self) -> None:
        self.exits = [
            Exit(0, 1224.0, 710.0, 44.0, 76.0),
            Exit(1, 1224.0, 430.0, 44.0, 76.0),
            Exit(2, 1224.0, 180.0, 44.0, 76.0),
        ]
        self.exit = (self.exits[0].x, self.exits[0].y)

    def _build_stalls(self) -> None:
        self.stalls.clear()
        count = max(1, self.config.stall_count)
        windows = self.menu_config.get("windows") or []
        flat_dishes = self.menu_config.get("dishes") or []

        # Build a shuffled list of window indices; repeat if we need more stalls than windows
        if windows:
            win_indices = list(range(len(windows)))
            self.rng.shuffle(win_indices)
        else:
            win_indices = []

        left = 160.0
        right = self.width - 170.0
        gap = 0.0 if count == 1 else (right - left) / (count - 1)
        for index in range(count):
            if windows and win_indices:
                win_idx = win_indices[index % len(win_indices)]
                window = windows[win_idx]
                stall_name = str(window.get("name", ""))
                dishes = self._build_stall_dishes_from_window(window)
            elif flat_dishes:
                stall_name = ""
                dishes = self._build_stall_dishes_flat(index)
            else:
                stall_name = ""
                dishes = []
            cook_time = self.rng.uniform(STALL_COOK_TIME_MIN_SECONDS, STALL_COOK_TIME_MAX_SECONDS)
            for dish in dishes:
                dish.cook_time = cook_time
            status = StallStatus.OPEN if dishes else StallStatus.SOLD_OUT
            self.stalls.append(
                Stall(
                    id=index,
                    x=left + gap * index,
                    y=86.0,
                    meat_ratio=self.rng.uniform(0.0, 1.0),
                    veg_ratio=self.rng.uniform(0.0, 1.0),
                    cook_time=cook_time,
                    name=stall_name,
                    status=status,
                    dishes=dishes,
                )
            )

    def _build_stall_dishes_from_window(self, window: dict[str, Any]) -> list[Dish]:
        """Build dishes from a window definition, picking up to dishes_per_stall dishes."""
        win_dishes = window.get("dishes") or []
        dishes_per_stall = int(self.menu_config.get("dishes_per_stall", 4))
        price_jitter = self.menu_config.get("price_jitter", (-0.5, 0.8))
        cook_time_jitter = self.menu_config.get("cook_time_jitter", (-2.0, 3.0))
        count = min(dishes_per_stall, len(win_dishes))
        if count == 0:
            return []
        # Shuffle and pick 'count' dishes from the window
        shuffled = list(win_dishes)
        self.rng.shuffle(shuffled)
        selected = shuffled[:count]
        dishes: list[Dish] = []
        for dish_data in selected:
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

    def _build_stall_dishes_flat(self, stall_index: int) -> list[Dish]:
        """Legacy: build dishes from a flat dish list using round-robin assignment."""
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
        gap_y = 108.0
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
            (self.width - 70.0, 548.0, 52.0, 96.0),
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

        spawn_duration = self._student_spawn_cutoff_time()
        if spawn_duration <= 0:
            return self.config.total_student_count
        if self.game_time > spawn_duration:
            return self.spawned_students

        progress = clamp(self.game_time / spawn_duration, 0.0, 1.0)
        if progress <= 0.5:
            distribution = 2.0 * progress * progress
        else:
            distribution = 1.0 - 2.0 * (1.0 - progress) * (1.0 - progress)
        return min(self.config.total_student_count, round(distribution * self.config.total_student_count))

    def _student_spawn_cutoff_time(self) -> float:
        return self.config.duration_game_seconds / 2.0

    def _choose_group_size(self) -> int:
        pair_probability, multi_probability = self.config.resolved_companion_group_probabilities()
        roll = self.rng.random()
        if roll < multi_probability:
            return self.rng.choice([3, 4])
        if roll < multi_probability + pair_probability:
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
        veg_pref = clamp(1.0 - meat_pref + self.rng.uniform(-0.30, 0.30), 0.0, 1.0)  # 荤素负相关，模拟真实偏好
        shared_preferences = {
            "meat": meat_pref,
            "veg": veg_pref,
            "price_sensitivity": self.rng.uniform(0.2, 1.0),
            "wait_tolerance": self.rng.uniform(0.2, 1.0),
            "spicy": self.rng.betavariate(2.0, 5.0),  # 辣度偏好偏右分布，大多数人偏淡
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
            eating_duration=self._sample_eating_time(),
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

    def _sample_eating_time(self) -> float:
        for _ in range(100):
            value = self.rng.gauss(EATING_TIME_MEAN_SECONDS, EATING_TIME_STDDEV_SECONDS)
            if EATING_TIME_MIN_SECONDS <= value <= EATING_TIME_MAX_SECONDS:
                return value
        return clamp(value, EATING_TIME_MIN_SECONDS, EATING_TIME_MAX_SECONDS)

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
                score = self._dish_preference_cost(student, dish) + self._stall_choice_cost(student, stall, dish)
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
        queue_cost = len(stall.queue) * (1.1 - wait_tolerance) * 2.0
        corridor_x = (student.x + stall.x) / 2.0
        corridor_y = (student.y + self.queue_walkway_y) / 2.0
        corridor_density = self._density_near(corridor_x, corridor_y, 120.0)
        congestion_cost = self._density_near(stall.x, stall.y + 110.0, 105.0) * 0.35
        cook_cost = stall.cook_time * 0.015
        price_cost = dish.price * student.preferences.get("price_sensitivity", 0.5) * 0.04
        return (
            queue_cost
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
        navigation_path_tasks: list[
            tuple[Student, tuple[float, float], tuple[float, float], str]
        ] = []
        table_path_tasks: list[
            tuple[Student, tuple[float, float], Table, int, float, float]
        ] = []
        self._start_due_queue_paths_parallel()
        self._refresh_moving_queue_targets_parallel()
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
                self._send_student_to_table(
                    student,
                    table_path_tasks=table_path_tasks,
                    navigation_path_tasks=navigation_path_tasks,
                )
            elif student.state == StudentState.WAITING_SEAT:
                self._send_student_to_table(
                    student,
                    table_path_tasks=table_path_tasks,
                    navigation_path_tasks=navigation_path_tasks,
                )
                self._move_student(student, game_delta, student.walk_speed)
            elif student.state == StudentState.MOVING_TO_SEAT:
                arrived = self._move_student(student, game_delta, student.table_walk_speed)
                if arrived:
                    self._snap_student_to_reserved_seat(student)
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
                        game_time=student.eating_done_at,
                    )
                    self._snap_student_to_seat_access(student)
                    self._release_seat(student)
                    self._set_tray_return_path(student, navigation_path_tasks)
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
                    self._set_exit_path(student, navigation_path_tasks)
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

        self._run_table_path_tasks(table_path_tasks)
        self._run_navigation_path_tasks(navigation_path_tasks)
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
            index = len(stall.queue) + self._inbound_queue_rank(student)
        return self._queue_slot_position(stall, index)

    def _inbound_queue_rank(self, student: Student) -> int:
        if student.stall_id is None:
            return 0
        inbound = [
            candidate
            for candidate in self.students.values()
            if candidate.stall_id == student.stall_id
            and candidate.state == StudentState.MOVING_TO_QUEUE
            and candidate.id not in self.stalls[student.stall_id].queue
        ]
        inbound.sort(key=self._inbound_queue_sort_key)
        for index, candidate in enumerate(inbound):
            if candidate.id == student.id:
                return index
        return len(inbound)

    def _inbound_queue_sort_key(self, student: Student) -> tuple[float, float, int]:
        path_started_at = student.path_started_at if student.path_started_at is not None else self.game_time
        return path_started_at, student.spawn_time, student.id

    def _queue_slot_position(self, stall: Stall, index: int) -> tuple[float, float]:
        if index <= 6:
            return stall.x, stall.y + 76.0 + index * 24.0

        overflow_index = index - 7
        side = -1.0 if overflow_index % 2 == 0 else 1.0
        lane = overflow_index // 2 + 1
        x = stall.x + side * lane * 32.0
        y = min(self.top_walkway_y + 46.0, self.bottom_walkway_y - 80.0)
        x = max(64.0, min(self.width - 64.0, x))
        return self._nearest_static_walkable_position(x, y)

    def _start_queue_path(self, student: Student, *, force: bool = False) -> None:
        target = self._queue_target_position(student)
        if target is None or student.stall_id is None:
            return
        self._set_navigation_path(student, target, force=force)

    def _refresh_moving_queue_targets_parallel(self) -> None:
        tasks: list[tuple[Student, tuple[float, float], tuple[float, float]]] = []
        for student in self.students.values():
            if student.state != StudentState.MOVING_TO_QUEUE:
                continue
            self._refresh_moving_queue_target(student, tasks)
        self._run_queue_refresh_path_tasks(tasks)

    def _refresh_moving_queue_target(
        self,
        student: Student,
        queue_refresh_path_tasks: list[
            tuple[Student, tuple[float, float], tuple[float, float]]
        ] | None = None,
    ) -> None:
        target = self._queue_target_position(student)
        if target is None:
            return

        target_x, target_y = target
        if not student.path:
            student.target_x = target_x
            student.target_y = target_y
            return

        current_end_x, current_end_y = student.path[-1]
        target_shift = distance(current_end_x, current_end_y, target_x, target_y)
        if target_shift <= 4.0:
            return

        candidate_path = [*student.path[:-1], target]
        if self._path_crosses_static_blocking_obstacle(
            (student.x, student.y),
            candidate_path,
            ignored_student_id=student.id,
        ):
            if not self._should_replan_queue_target(student, target, target_shift):
                student.path[-1] = target
                student.path_goal = target
                if len(student.path) == 1:
                    student.target_x = target_x
                    student.target_y = target_y
                return
            if queue_refresh_path_tasks is not None:
                queue_refresh_path_tasks.append((student, (student.x, student.y), target))
                return
            path = self._build_navigation_path((student.x, student.y), target, ignored_student_id=student.id)
            if path:
                self._set_path(student, path)
                student.path_length = self._path_distance(student.x, student.y, student.path)
                student.reroute_count += 1
            return

        student.path[-1] = target
        student.path_goal = target
        if len(student.path) == 1:
            student.target_x = target_x
            student.target_y = target_y

    def _should_replan_queue_target(
        self,
        student: Student,
        target: tuple[float, float],
        target_shift: float,
    ) -> bool:
        if student.path_planned_at is None:
            return True
        if self.game_time - student.path_planned_at >= PATH_REPLAN_COOLDOWN_SECONDS:
            return True
        if target_shift >= QUEUE_TARGET_REPLAN_SHIFT:
            return True
        if distance(student.x, student.y, target[0], target[1]) <= QUEUE_TARGET_REPLAN_NEAR_DISTANCE:
            return True
        return False

    def _run_queue_refresh_path_tasks(
        self,
        tasks: list[tuple[Student, tuple[float, float], tuple[float, float]]],
    ) -> None:
        if not tasks:
            return

        requests = [
            (start, target, student.id)
            for student, start, target in tasks
        ]
        paths = self._build_navigation_paths_parallel(requests)
        for (student, start, _target), path in zip(tasks, paths):
            if not path:
                continue
            self._set_path(student, path)
            student.path_goal = _target
            student.path_planned_at = self.game_time
            student.path_length = self._path_distance(start[0], start[1], student.path)
            student.reroute_count += 1

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
        self._clear_path_metadata(student)

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
        ready_at = started_at + stall.cook_time
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

    def _send_student_to_table(
        self,
        student: Student,
        table_path_tasks: list[
            tuple[Student, tuple[float, float], Table, int, float, float]
        ] | None = None,
        navigation_path_tasks: list[
            tuple[Student, tuple[float, float], tuple[float, float], str]
        ] | None = None,
    ) -> None:
        free: list[tuple[Table, int]] = []
        for table in self.tables:
            for seat_index in table.free_seat_indexes():
                free.append((table, seat_index))
        if not free:
            if student.waiting_seat_since is None:
                student.waiting_seat_since = self.game_time
            if self.game_time - student.waiting_seat_since >= MAX_SEAT_WAIT_SECONDS:
                self._send_student_to_exit(
                    student,
                    reason="seat_wait_timeout",
                    navigation_path_tasks=navigation_path_tasks,
                )
                return
            if student.state != StudentState.WAITING_SEAT:
                student.state = StudentState.WAITING_SEAT
                wait_target = (self.width - 70.0, self.top_walkway_y)
                if navigation_path_tasks is None:
                    self._set_navigation_path(student, wait_target)
                else:
                    self._queue_navigation_path_task(
                        navigation_path_tasks,
                        student,
                        wait_target,
                        student.state.value,
                    )
                return
            student.state = StudentState.WAITING_SEAT
            return

        student.waiting_seat_since = None
        table, seat_index, seat_x, seat_y = self._best_seat_assignment_candidate(student, free)
        self._reserve_student_seat(student, table, seat_index)
        if table_path_tasks is not None:
            table_path_tasks.append(
                (
                    student,
                    (student.x, student.y),
                    table,
                    seat_index,
                    seat_x,
                    seat_y,
                )
            )
            return

        path = self._build_table_path(student.x, student.y, table, seat_index, seat_x, seat_y)
        walk_distance = self._path_distance(student.x, student.y, path)
        self._start_student_seat_move(student, table, seat_index, path, walk_distance, (student.x, student.y))

    def _reserve_student_seat(self, student: Student, table: Table, seat_index: int) -> None:
        seat = table.seats[seat_index]
        seat.status = SeatStatus.RESERVED
        seat.student_id = student.id
        student.table_id = table.id
        student.seat_index = seat_index

    def _start_student_seat_move(
        self,
        student: Student,
        table: Table,
        seat_index: int,
        path: list[tuple[float, float]],
        walk_distance: float,
        start: tuple[float, float],
    ) -> None:
        self._reserve_student_seat(student, table, seat_index)
        self._set_path(student, path)
        student.path_goal = path[-1] if path else None
        student.path_planned_at = self.game_time
        self._start_path_tracking(
            student,
            path,
            start=start,
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

    def _best_seat_assignment_candidate(
        self,
        student: Student,
        free: list[tuple[Table, int]],
    ) -> tuple[Table, int, float, float]:
        best: tuple[float, Table, int, float, float] | None = None
        for table, seat_index in free:
            seat_x, seat_y = self._seat_position(table, seat_index)
            access_x, access_y = self._seat_access_position(table, seat_index)
            estimated_walk_distance = self._estimated_walk_distance(student.x, student.y, access_x, access_y)
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
        return table, seat_index, seat_x, seat_y

    def _best_seat_candidate(
        self,
        student: Student,
        free: list[tuple[Table, int]],
    ) -> tuple[Table, int, list[tuple[float, float]], float]:
        table, seat_index, seat_x, seat_y = self._best_seat_assignment_candidate(student, free)
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

    def _snap_student_to_reserved_seat(self, student: Student) -> None:
        if student.table_id is None or student.seat_index is None:
            return
        table = self.tables[student.table_id]
        seat_x, seat_y = self._seat_position(table, student.seat_index)
        student.x = seat_x
        student.y = seat_y
        student.target_x = seat_x
        student.target_y = seat_y
        student.path.clear()
        self._clear_path_metadata(student)
        self._complete_path_tracking(student)

    def _snap_student_to_seat_access(self, student: Student) -> None:
        if student.table_id is None or student.seat_index is None:
            return
        table = self.tables[student.table_id]
        old_x, old_y = student.x, student.y
        access_x, access_y = self._seat_access_position(table, student.seat_index)
        student.x = access_x
        student.y = access_y
        student.target_x = access_x
        student.target_y = access_y
        student.path.clear()
        self._clear_path_metadata(student)
        moved = distance(old_x, old_y, access_x, access_y)
        if moved > 0.2:
            student.facing_x = (access_x - old_x) / moved
            student.facing_y = (access_y - old_y) / moved

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
            return TABLE_SEAT_OFFSETS[2]
        if seat_count <= 4:
            return TABLE_SEAT_OFFSETS[4]
        return TABLE_SEAT_OFFSETS[6][:seat_count]

    def _build_table_path(
        self,
        start_x: float,
        start_y: float,
        table: Table,
        seat_index: int,
        seat_x: float,
        seat_y: float,
    ) -> list[tuple[float, float]]:
        start = (start_x, start_y)
        side_step = self._post_pickup_side_step_position(start_x, start_y, table)
        if side_step is None:
            return self._build_navigation_path(start, self._seat_access_position(table, seat_index))

        seat_path = self._build_navigation_path(side_step, self._seat_access_position(table, seat_index))
        return self._compact_path([side_step, *seat_path])

    def _post_pickup_side_step_position(
        self,
        start_x: float,
        start_y: float,
        table: Table,
    ) -> tuple[float, float] | None:
        preferred_side = 1.0 if table.x >= start_x else -1.0
        for side in (preferred_side, -preferred_side):
            for side_step in (72.0, 96.0, 120.0):
                candidate_x = max(64.0, min(self.width - 64.0, start_x + side * side_step))
                candidate_y = max(64.0, min(self.height - 64.0, start_y))
                if distance(start_x, start_y, candidate_x, candidate_y) <= 3.0:
                    continue
                if self._is_static_walkable_point(candidate_x, candidate_y):
                    return candidate_x, candidate_y
        return None

    def _seat_access_position(self, table: Table, seat_index: int) -> tuple[float, float]:
        seat_x, seat_y = self._seat_position(table, seat_index)
        side_x = self._adjacent_aisle_x(table, seat_index)
        access_y = self._seat_access_y(table, seat_index)
        if abs(seat_y - table.y) <= 8.0:
            candidates = [
                (side_x, seat_y),
                (side_x, access_y),
                (seat_x, access_y),
            ]
        elif seat_y > table.y and self._lower_table_access_is_constrained(table):
            candidates = [
                (seat_x, access_y),
                (side_x, access_y),
                (side_x, seat_y),
            ]
        else:
            candidates = [
                (seat_x, access_y),
                (side_x, seat_y),
                (side_x, access_y),
            ]
        for candidate in candidates:
            if self._is_static_walkable_point(candidate[0], candidate[1]):
                return candidate
        return self._nearest_static_walkable_position(candidates[0][0], candidates[0][1])

    def _nearest_static_walkable_position(self, x: float, y: float) -> tuple[float, float]:
        x = max(64.0, min(self.width - 64.0, x))
        y = max(64.0, min(self.height - 64.0, y))
        if self._is_static_walkable_point(x, y):
            return x, y

        for radius in (18.0, 36.0, 54.0, 72.0, 96.0, 128.0):
            candidates = [
                (x + radius, y),
                (x - radius, y),
                (x, y + radius),
                (x, y - radius),
                (x + radius, y + radius),
                (x + radius, y - radius),
                (x - radius, y + radius),
                (x - radius, y - radius),
            ]
            for candidate_x, candidate_y in candidates:
                candidate_x = max(64.0, min(self.width - 64.0, candidate_x))
                candidate_y = max(64.0, min(self.height - 64.0, candidate_y))
                if self._is_static_walkable_point(candidate_x, candidate_y):
                    return candidate_x, candidate_y
        return x, y

    def _set_exit_path(
        self,
        student: Student,
        navigation_path_tasks: list[
            tuple[Student, tuple[float, float], tuple[float, float], str]
        ] | None = None,
        kind: str | None = None,
        force: bool = False,
    ) -> None:
        exit_area = self._choose_exit(student)
        student.exit_id = exit_area.id
        exit_point = (exit_area.x, exit_area.y)
        if navigation_path_tasks is None:
            self._set_navigation_path(student, exit_point, force=force)
            return
        self._queue_navigation_path_task(
            navigation_path_tasks,
            student,
            exit_point,
            kind or student.state.value,
        )

    def _send_student_to_exit(
        self,
        student: Student,
        reason: str,
        navigation_path_tasks: list[
            tuple[Student, tuple[float, float], tuple[float, float], str]
        ] | None = None,
    ) -> None:
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
        self._set_exit_path(
            student,
            navigation_path_tasks=navigation_path_tasks,
            kind=previous_state.value if isinstance(previous_state, StudentState) else str(previous_state),
        )
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

    def _set_tray_return_path(
        self,
        student: Student,
        navigation_path_tasks: list[
            tuple[Student, tuple[float, float], tuple[float, float], str]
        ] | None = None,
        kind: str | None = None,
        force: bool = False,
    ) -> None:
        point = self._nearest_tray_return_center(student.x, student.y)
        if navigation_path_tasks is None:
            self._set_navigation_path(student, point, force=force)
            return
        self._queue_navigation_path_task(
            navigation_path_tasks,
            student,
            point,
            kind or student.state.value,
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
        seat_x, _ = self._seat_position(table, seat_index)
        if seat_x < table.x:
            return max(92.0, table.x - 92.5 if column > 0 else 92.0)
        return min(self.width - 64.0, table.x + 92.5)

    def _seat_access_y(self, table: Table, seat_index: int) -> float:
        _, seat_y = self._seat_position(table, seat_index)
        if seat_y < table.y:
            return max(self.top_walkway_y, table.y - 56.0)
        if self._lower_table_access_is_constrained(table):
            return max(self.top_walkway_y, table.y - 56.0)
        return min(self.height - 64.0, table.y + 56.0)

    def _lower_table_access_is_constrained(self, table: Table) -> bool:
        obstacle_height = TABLE_OBSTACLE_SIZES.get(table.seat_count, TABLE_OBSTACLE_SIZES[4])[1]
        lower_clearance = self.height - 64.0 - (table.y + obstacle_height / 2.0)
        return lower_clearance < 72.0

    def _set_navigation_path(
        self,
        student: Student,
        target: tuple[float, float],
        *,
        force: bool = False,
    ) -> None:
        start = (student.x, student.y)
        if not force and self._reuse_current_path(student, target):
            return
        path = self._build_navigation_path(
            start,
            target,
            ignored_student_id=student.id,
        )
        self._apply_navigation_path(
            student,
            path,
            start=start,
            target=target,
            kind=student.state.value,
        )

    def _queue_navigation_path_task(
        self,
        tasks: list[tuple[Student, tuple[float, float], tuple[float, float], str]],
        student: Student,
        target: tuple[float, float],
        kind: str,
    ) -> None:
        tasks.append((student, (student.x, student.y), target, kind))

    def _run_navigation_path_tasks(
        self,
        tasks: list[tuple[Student, tuple[float, float], tuple[float, float], str]],
    ) -> None:
        if not tasks:
            return

        pending: list[tuple[Student, tuple[float, float], tuple[float, float], str]] = []
        for student, start, target, kind in tasks:
            if self._reuse_current_path(student, target):
                continue
            pending.append((student, start, target, kind))
        if not pending:
            return

        requests = [
            (start, target, student.id)
            for student, start, target, _kind in pending
        ]
        paths = self._build_navigation_paths_parallel(requests)
        for (student, start, _target, kind), path in zip(pending, paths):
            self._apply_navigation_path(
                student,
                path,
                start=start,
                target=_target,
                kind=kind,
            )

    def _run_table_path_tasks(
        self,
        tasks: list[tuple[Student, tuple[float, float], Table, int, float, float]],
    ) -> None:
        if not tasks:
            return

        path_requests: list[tuple[tuple[float, float], tuple[float, float], int | None]] = []
        prefixes: list[list[tuple[float, float]]] = []
        for student, start, table, seat_index, _seat_x, _seat_y in tasks:
            side_step = self._post_pickup_side_step_position(start[0], start[1], table)
            access_position = self._seat_access_position(table, seat_index)
            if side_step is None:
                prefixes.append([])
                path_requests.append((start, access_position, None))
            else:
                prefixes.append([side_step])
                path_requests.append((side_step, access_position, None))

        paths = self._build_navigation_paths_parallel(path_requests)
        for task, prefix, path in zip(tasks, prefixes, paths):
            student, start, table, seat_index, _seat_x, _seat_y = task
            full_path = self._compact_path([*prefix, *path])
            walk_distance = self._path_distance(start[0], start[1], full_path)
            self._start_student_seat_move(
                student,
                table,
                seat_index,
                full_path,
                walk_distance,
                start,
            )

    def _start_due_queue_paths_parallel(self) -> None:
        students: list[Student] = []
        requests: list[tuple[tuple[float, float], tuple[float, float], int | None]] = []
        for student in self.students.values():
            if student.state != StudentState.DECIDING or self.game_time < student.decision_done_at:
                continue
            if student.stall_id is None:
                continue
            student.state = StudentState.MOVING_TO_QUEUE
            students.append(student)

        for student in students:
            target = self._queue_target_position(student)
            if target is None:
                continue
            requests.append(((student.x, student.y), target, student.id))

        if not requests:
            return

        paths = self._build_navigation_paths_parallel(requests)
        for student, request, path in zip(students, requests, paths):
            start, target, _ = request
            self._apply_navigation_path(
                student,
                path,
                start=start,
                target=target,
                kind=student.state.value,
            )

    def _build_navigation_path(
        self,
        start: tuple[float, float],
        target: tuple[float, float],
        ignored_student_id: int | None = None,
    ) -> list[tuple[float, float]]:
        pathfinder = self._navigation_pathfinder()
        foot_start = self._foot_point_from_position(start[0], start[1])
        foot_target = self._foot_point_from_position(target[0], target[1])
        foot_path = pathfinder.find_path(
            foot_start,
            foot_target,
            self._navigation_congestion_points(ignored_student_id),
            self._navigation_dynamic_obstacles(ignored_student_id, foot_start, foot_target),
        )
        return self._compact_path([(x, y - STUDENT_COLLISION_FOOT_OFFSET_Y) for x, y in foot_path])

    def _build_navigation_path_to_reachable_target(
        self,
        start: tuple[float, float],
        target: tuple[float, float],
        ignored_student_id: int | None = None,
    ) -> tuple[list[tuple[float, float]], tuple[float, float], bool]:
        pathfinder = self._navigation_pathfinder()
        foot_start = self._foot_point_from_position(start[0], start[1])
        foot_target = self._foot_point_from_position(target[0], target[1])
        foot_path, reachable_foot_target, target_reachable = pathfinder.find_path_to_reachable_target(
            foot_start,
            foot_target,
            self._navigation_congestion_points(ignored_student_id),
            self._navigation_dynamic_obstacles(ignored_student_id, foot_start, foot_target),
        )
        path = self._compact_path([(x, y - STUDENT_COLLISION_FOOT_OFFSET_Y) for x, y in foot_path])
        reachable_target = (
            reachable_foot_target[0],
            reachable_foot_target[1] - STUDENT_COLLISION_FOOT_OFFSET_Y,
        )
        return path, reachable_target, target_reachable

    def _build_navigation_paths_parallel(
        self,
        requests: list[tuple[tuple[float, float], tuple[float, float], int | None]],
    ) -> list[list[tuple[float, float]]]:
        if not requests:
            return []

        pathfinder = self._navigation_pathfinder()
        congestion_point_items = self._navigation_congestion_point_items()
        foot_requests = []
        for start, target, ignored_student_id in requests:
            foot_start = self._foot_point_from_position(start[0], start[1])
            foot_target = self._foot_point_from_position(target[0], target[1])
            foot_requests.append(
                (
                    foot_start,
                    foot_target,
                    self._navigation_congestion_points_from_items(
                        congestion_point_items,
                        ignored_student_id,
                    ),
                    self._navigation_dynamic_obstacles(
                        ignored_student_id,
                        foot_start,
                        foot_target,
                    ),
                )
            )
        return [
            self._compact_path([(x, y - STUDENT_COLLISION_FOOT_OFFSET_Y) for x, y in foot_path])
            for foot_path in pathfinder.find_paths_parallel(foot_requests)
        ]

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
        return self._navigation_congestion_points_from_items(
            self._navigation_congestion_point_items(),
            ignored_student_id,
        )

    def _navigation_congestion_point_items(self) -> list[tuple[int, tuple[float, float]]]:
        return [
            (student.id, self._student_foot_point(student))
            for student in self.students.values()
            if student.state not in (StudentState.QUEUED, StudentState.EATING, StudentState.DONE)
        ]

    def _navigation_congestion_points_from_items(
        self,
        items: list[tuple[int, tuple[float, float]]],
        ignored_student_id: int | None = None,
    ) -> list[tuple[float, float]]:
        return [
            point
            for student_id, point in items
            if student_id != ignored_student_id
        ]

    def _navigation_dynamic_obstacles(
        self,
        ignored_student_id: int | None = None,
        start: tuple[float, float] | None = None,
        target: tuple[float, float] | None = None,
    ) -> list[NavRect]:
        bounds: tuple[float, float, float, float] | None = None
        if start is not None and target is not None:
            padding = 140.0
            bounds = (
                min(start[0], target[0]) - padding,
                min(start[1], target[1]) - padding,
                max(start[0], target[0]) + padding,
                max(start[1], target[1]) + padding,
            )

        obstacles: list[NavRect] = []
        for student in self._collision_students(ignored_student_id):
            left, top, right, bottom = self._student_collision_rect(student)
            if bounds is not None and not self._rects_overlap((left, top, right, bottom), bounds):
                continue
            kind = "queued_student" if student.state == StudentState.QUEUED else "student"
            obstacles.append(NavRect(left, top, right, bottom, kind))
        return obstacles

    def _set_path(self, student: Student, path: list[tuple[float, float]]) -> None:
        student.path = self._compact_path(path)
        if student.path:
            student.target_x, student.target_y = student.path[0]

    def _clear_path_metadata(self, student: Student) -> None:
        student.path_goal = None
        student.path_planned_at = None

    def _apply_navigation_path(
        self,
        student: Student,
        path: list[tuple[float, float]],
        start: tuple[float, float],
        target: tuple[float, float],
        kind: str,
    ) -> None:
        self._set_path(student, path)
        student.path_goal = target
        student.path_planned_at = self.game_time
        self._start_path_tracking(student, path, start=start, kind=kind)

    def _reuse_current_path(self, student: Student, target: tuple[float, float]) -> bool:
        if not student.path:
            return False
        if student.path_goal is None:
            return False
        if distance(student.path_goal[0], student.path_goal[1], target[0], target[1]) > PATH_REUSE_TARGET_TOLERANCE:
            return False
        if self._path_crosses_static_blocking_obstacle(
            (student.x, student.y),
            list(student.path),
            ignored_student_id=student.id,
        ):
            return False
        student.path[-1] = target
        student.path_goal = target
        if len(student.path) == 1:
            student.target_x, student.target_y = target
        return True

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
        self._clear_path_metadata(student)

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
        return student.x, student.y + STUDENT_COLLISION_FOOT_OFFSET_Y

    def _foot_point_from_position(self, x: float, y: float) -> tuple[float, float]:
        return x, y + STUDENT_COLLISION_FOOT_OFFSET_Y

    def _student_uses_collision_box(self, student: Student) -> bool:
        return student.state not in (StudentState.EATING, StudentState.DONE)

    def _collision_students(self, ignored_student_id: int | None = None) -> list[Student]:
        return [
            student
            for student in self.students.values()
            if student.id != ignored_student_id and self._student_uses_collision_box(student)
        ]

    def _student_collision_rect(self, student: Student) -> tuple[float, float, float, float]:
        return self._student_collision_rect_from_position(student.x, student.y)

    def _student_collision_rect_from_position(self, x: float, y: float) -> tuple[float, float, float, float]:
        foot_x, foot_y = self._foot_point_from_position(x, y)
        half_width = STUDENT_COLLISION_WIDTH / 2.0
        half_height = STUDENT_COLLISION_HEIGHT / 2.0
        return (
            foot_x - half_width,
            foot_y - half_height,
            foot_x + half_width,
            foot_y + half_height,
        )

    def _student_collision_blocked(
        self,
        student: Student,
        x: float,
        y: float,
        ignored_student_ids: set[int] | None = None,
    ) -> bool:
        if not self._student_uses_collision_box(student):
            return False
        ignored_student_ids = ignored_student_ids or set()
        foot_x, foot_y = self._foot_point_from_position(x, y)
        current_foot_x, current_foot_y = self._student_foot_point(student)
        padded_width = STUDENT_COLLISION_WIDTH + STUDENT_COLLISION_PADDING
        padded_height = STUDENT_COLLISION_HEIGHT + STUDENT_COLLISION_PADDING
        for other in self._collision_students(student.id):
            if other.id in ignored_student_ids:
                continue
            other_foot_x, other_foot_y = self._student_foot_point(other)
            candidate_dx = abs(foot_x - other_foot_x)
            candidate_dy = abs(foot_y - other_foot_y)
            if candidate_dx >= padded_width or candidate_dy >= padded_height:
                continue

            current_dx = abs(current_foot_x - other_foot_x)
            current_dy = abs(current_foot_y - other_foot_y)
            candidate_core_overlap = (
                candidate_dx < STUDENT_COLLISION_WIDTH
                and candidate_dy < STUDENT_COLLISION_HEIGHT
            )
            current_core_overlap = (
                current_dx < STUDENT_COLLISION_WIDTH
                and current_dy < STUDENT_COLLISION_HEIGHT
            )
            candidate_pressure = min(padded_width - candidate_dx, padded_height - candidate_dy)
            current_pressure = min(
                max(0.0, padded_width - current_dx),
                max(0.0, padded_height - current_dy),
            )
            if not candidate_core_overlap and candidate_pressure <= current_pressure + 0.1:
                continue
            if current_core_overlap and candidate_core_overlap and candidate_pressure <= current_pressure + 0.1:
                continue
            if candidate_core_overlap or candidate_pressure > current_pressure + 0.1:
                return True
        return False

    def _can_place_student_at(
        self,
        student: Student,
        x: float,
        y: float,
        ignored_student_ids: set[int] | None = None,
    ) -> bool:
        return (
            self._is_static_walkable_point(x, y)
            and not self._student_collision_blocked(student, x, y, ignored_student_ids)
        )

    def _try_place_student_at(
        self,
        student: Student,
        x: float,
        y: float,
        ignored_student_ids: set[int] | None = None,
    ) -> bool:
        x = max(28.0, min(self.width - 28.0, x))
        y = max(28.0, min(self.height - 28.0, y))
        if not self._can_place_student_at(student, x, y, ignored_student_ids):
            return False
        student.x = x
        student.y = y
        return True

    def _rects_overlap(
        self,
        first: tuple[float, float, float, float],
        second: tuple[float, float, float, float],
        padding: float = 0.0,
    ) -> bool:
        return (
            min(first[2], second[2]) + padding > max(first[0], second[0])
            and min(first[3], second[3]) + padding > max(first[1], second[1])
        )

    def _expand_rect(
        self,
        rect: tuple[float, float, float, float],
        padding_x: float,
        padding_y: float,
    ) -> tuple[float, float, float, float]:
        return (
            rect[0] - padding_x,
            rect[1] - padding_y,
            rect[2] + padding_x,
            rect[3] + padding_y,
        )

    def _segment_intersects_rect(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        rect: tuple[float, float, float, float],
    ) -> bool:
        start_x, start_y = start
        end_x, end_y = end
        left, top, right, bottom = rect
        delta_x = end_x - start_x
        delta_y = end_y - start_y
        t_min = 0.0
        t_max = 1.0

        for direction, lower, upper in (
            (delta_x, left - start_x, right - start_x),
            (delta_y, top - start_y, bottom - start_y),
        ):
            if abs(direction) <= 1e-9:
                if lower > 0.0 or upper < 0.0:
                    return False
                continue

            near = lower / direction
            far = upper / direction
            if near > far:
                near, far = far, near
            t_min = max(t_min, near)
            t_max = min(t_max, far)
            if t_min > t_max:
                return False
        return True

    def _move_student(self, student: Student, game_delta: float, speed: float) -> bool:
        if student.path:
            student.target_x, student.target_y = student.path[0]

        old_x, old_y = student.x, student.y
        target_distance = distance(student.x, student.y, student.target_x, student.target_y)
        step_distance = speed * game_delta
        arrival_radius = 3.0 if not student.path else 5.5
        blocked_by_dynamic_student = False
        used_local_avoidance = False
        endpoint_repaired = False
        if target_distance <= max(arrival_radius, step_distance):
            arrived = self._try_place_student_at(student, student.target_x, student.target_y)
            if arrived:
                student.x, student.y = student.target_x, student.target_y
            else:
                target_is_static_walkable = self._is_static_walkable_point(
                    student.target_x,
                    student.target_y,
                )
                if target_is_static_walkable:
                    blocked_by_dynamic_student = True
                    if self._try_local_avoidance_step(student, step_distance):
                        blocked_by_dynamic_student = False
                        used_local_avoidance = True
                else:
                    if self.game_time < student.detour_until or not self._try_static_obstacle_detour(student):
                        self._reroute_student(student)
                arrived = False
        else:
            next_x, next_y, arrived = move_towards(
                student.x,
                student.y,
                student.target_x,
                student.target_y,
                step_distance,
            )
            if self._try_place_student_at(student, next_x, next_y):
                pass
            elif self._is_static_walkable_point(next_x, next_y):
                arrived = False
                if self._is_entrance_release_step(student, next_x, next_y):
                    student.x = next_x
                    student.y = next_y
                else:
                    blocked_by_dynamic_student = True
                if blocked_by_dynamic_student and self._try_local_avoidance_step(student, step_distance):
                    blocked_by_dynamic_student = False
                    used_local_avoidance = True
            elif (
                self.game_time >= student.detour_until
                and (self._try_static_obstacle_detour(student) or self._reroute_student(student))
            ):
                student.detour_until = self.game_time + 2.0
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
        if (
            (target_distance > 18.0 or blocked_by_dynamic_student)
            and student.actual_speed < max(1.2, speed * 0.18)
        ):
            student.stuck_time += game_delta
        else:
            student.stuck_time = max(0.0, student.stuck_time - game_delta * 1.8)
        if self._student_table_overlap_obstacle(student) is not None:
            student.table_overlap_time += game_delta
        else:
            student.table_overlap_time = 0.0
        if used_local_avoidance:
            student.local_avoidance_time += game_delta
            student.local_avoidance_count += 1
            if student.local_avoidance_count >= LOCAL_AVOIDANCE_REACHABILITY_CHECK_COUNT:
                endpoint_repaired = self._repair_unreachable_path_endpoint(student)
                student.local_avoidance_count = 0
        else:
            student.local_avoidance_time = max(0.0, student.local_avoidance_time - game_delta * 2.0)
            student.local_avoidance_count = 0
        student.last_x = student.x
        student.last_y = student.y

        if endpoint_repaired:
            return False

        if (
            student.table_overlap_time >= TABLE_OVERLAP_RELOCATION_SECONDS
            and self._try_relocate_from_table_obstacle(student)
        ):
            return False

        if student.stuck_time >= STUCK_RECOVERY_SECONDS and self._try_recover_stuck_student(student):
            return False

        if student.local_avoidance_time >= LOCAL_AVOIDANCE_REROUTE_SECONDS:
            if self._try_static_obstacle_detour(student):
                pass
            elif self._reroute_student(student):
                student.reroute_count += 1
                student.detour_until = self.game_time + 2.0
            student.local_avoidance_time = 0.0
            student.local_avoidance_count = 0
            student.stuck_time = 0.0
            return False

        if blocked_by_dynamic_student and student.stuck_time >= 1.6:
            self._try_start_detour(student, self._collision_students())

        if arrived and student.path:
            student.path.pop(0)
            if student.path:
                student.target_x, student.target_y = student.path[0]
                return False
        if arrived:
            self._complete_path_tracking(student)
        return arrived

    def _try_recover_stuck_student(self, student: Student) -> bool:
        if student.state in (StudentState.QUEUED, StudentState.EATING, StudentState.DONE):
            return False

        if self._try_static_obstacle_detour(student):
            student.stuck_time = 0.0
            student.local_avoidance_time = 0.0
            student.local_avoidance_count = 0
            return True

        rerouted = self._reroute_student(student)
        if rerouted:
            student.reroute_count += 1
            student.detour_until = self.game_time + 2.0
        if rerouted:
            student.stuck_time = 0.0
            student.local_avoidance_time = 0.0
            student.local_avoidance_count = 0
            return True
        return False

    def _try_relocate_from_table_obstacle(self, student: Student) -> bool:
        if student.state in (StudentState.QUEUED, StudentState.EATING, StudentState.DONE):
            return False
        if self._student_table_overlap_obstacle(student) is None:
            student.table_overlap_time = 0.0
            return False

        empty_position = self._nearest_empty_position(student.x, student.y, ignored_student_id=student.id)
        if empty_position is None:
            return False

        old_x, old_y = student.x, student.y
        student.x, student.y = empty_position
        moved = distance(old_x, old_y, student.x, student.y)
        if moved > 0.2:
            student.facing_x = (student.x - old_x) / moved
            student.facing_y = (student.y - old_y) / moved

        detoured = self._try_static_obstacle_detour(student)
        rerouted = False
        if not detoured:
            rerouted = self._reroute_student(student)
        student.table_overlap_time = 0.0
        student.stuck_time = 0.0
        student.local_avoidance_time = 0.0
        student.local_avoidance_count = 0
        student.detour_until = self.game_time + 2.0
        if rerouted:
            student.reroute_count += 1
        return True

    def _student_table_overlap_obstacle(self, student: Student) -> dict[str, Any] | None:
        if student.state in (StudentState.QUEUED, StudentState.EATING, StudentState.DONE):
            return None

        student_rect = self._student_collision_rect(student)
        foot_x, foot_y = self._student_foot_point(student)
        for obstacle in self._obstacle_frames():
            if obstacle.get("kind") != "table":
                continue
            obstacle_rect = (
                float(obstacle["left"]),
                float(obstacle["top"]),
                float(obstacle["right"]),
                float(obstacle["bottom"]),
            )
            foot_inside = (
                obstacle_rect[0] <= foot_x <= obstacle_rect[2]
                and obstacle_rect[1] <= foot_y <= obstacle_rect[3]
            )
            if foot_inside or self._rects_overlap(student_rect, obstacle_rect):
                return obstacle
        return None

    def _nearest_empty_position(
        self,
        x: float,
        y: float,
        ignored_student_id: int | None = None,
    ) -> tuple[float, float] | None:
        x = max(64.0, min(self.width - 64.0, x))
        y = max(64.0, min(self.height - 64.0, y))
        students = self._collision_students(ignored_student_id)
        if self._is_walkable_point(x, y, students, ignored_student_id=ignored_student_id):
            return x, y

        directions = (
            (1.0, 0.0),
            (-1.0, 0.0),
            (0.0, 1.0),
            (0.0, -1.0),
            (1.0, 1.0),
            (1.0, -1.0),
            (-1.0, 1.0),
            (-1.0, -1.0),
        )
        for radius in (18.0, 30.0, 44.0, 60.0, 78.0, 96.0, 124.0, 156.0, 192.0):
            candidates: list[tuple[float, float]] = []
            for direction_x, direction_y in directions:
                length = (direction_x * direction_x + direction_y * direction_y) ** 0.5
                candidate_x = max(64.0, min(self.width - 64.0, x + direction_x / length * radius))
                candidate_y = max(64.0, min(self.height - 64.0, y + direction_y / length * radius))
                candidates.append((candidate_x, candidate_y))
            candidates.sort(key=lambda point: distance(point[0], point[1], x, y))
            for candidate_x, candidate_y in candidates:
                if self._is_walkable_point(candidate_x, candidate_y, students, ignored_student_id=ignored_student_id):
                    return candidate_x, candidate_y
        return None

    def _try_static_obstacle_detour(self, student: Student) -> bool:
        blocking_obstacle = self._path_blocking_static_obstacle(student)
        if blocking_obstacle is None:
            return False

        endpoint = student.path[-1] if student.path else (student.target_x, student.target_y)
        for detour_point in self._static_obstacle_detour_candidates(blocking_obstacle, endpoint):
            first_leg = self._build_navigation_path((student.x, student.y), detour_point, ignored_student_id=student.id)
            if not first_leg:
                continue
            if distance(first_leg[-1][0], first_leg[-1][1], detour_point[0], detour_point[1]) > 8.0:
                continue
            second_leg = self._build_navigation_path(detour_point, endpoint, ignored_student_id=student.id)
            path = self._compact_path([*first_leg, *second_leg])
            if not path:
                continue
            if self._path_still_crosses_obstacle((student.x, student.y), path, blocking_obstacle):
                continue
            self._set_path(student, path)
            student.reroute_count += 1
            student.detour_until = self.game_time + 2.0
            return True
        return False

    def _path_blocking_static_obstacle(self, student: Student) -> dict[str, Any] | None:
        start = self._student_foot_point(student)
        end = self._foot_point_from_position(student.target_x, student.target_y)
        for obstacle in self._static_blocking_obstacle_frames(ignored_student_id=student.id):
            rect = (
                float(obstacle["left"]),
                float(obstacle["top"]),
                float(obstacle["right"]),
                float(obstacle["bottom"]),
            )
            expanded = self._expand_rect(
                rect,
                STUDENT_COLLISION_WIDTH / 2.0 + STUDENT_COLLISION_PADDING,
                STUDENT_COLLISION_HEIGHT / 2.0 + STUDENT_COLLISION_PADDING,
            )
            if self._segment_intersects_rect(start, end, expanded):
                return obstacle
        return None

    def _static_blocking_obstacle_frames(
        self,
        ignored_student_id: int | None = None,
    ) -> list[dict[str, Any]]:
        obstacles = [
            item
            for item in self._obstacle_frames()
            if item.get("kind") == "table"
        ]
        for queued_student in self.students.values():
            if queued_student.id == ignored_student_id or queued_student.state != StudentState.QUEUED:
                continue
            left, top, right, bottom = self._student_collision_rect(queued_student)
            obstacles.append(
                {
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                    "kind": "queued_student",
                    "student_id": queued_student.id,
                }
            )
        return obstacles

    def _path_crosses_static_blocking_obstacle(
        self,
        start: tuple[float, float],
        path: list[tuple[float, float]],
        ignored_student_id: int | None = None,
    ) -> dict[str, Any] | None:
        for obstacle in self._static_blocking_obstacle_frames(ignored_student_id):
            if self._path_still_crosses_obstacle(start, path, obstacle):
                return obstacle
        return None

    def _static_obstacle_detour_candidates(
        self,
        obstacle: dict[str, Any],
        endpoint: tuple[float, float],
    ) -> list[tuple[float, float]]:
        left = float(obstacle["left"])
        top = float(obstacle["top"])
        right = float(obstacle["right"])
        bottom = float(obstacle["bottom"])
        center_x = (left + right) / 2.0
        center_y = (top + bottom) / 2.0
        clearance = max(44.0, LOCAL_AVOIDANCE_SIDE_STEP + STUDENT_COLLISION_PADDING)
        raw_candidates = [
            (left - clearance, top - clearance),
            (right + clearance, top - clearance),
            (left - clearance, bottom + clearance),
            (right + clearance, bottom + clearance),
            (center_x, top - clearance),
            (center_x, bottom + clearance),
            (left - clearance, center_y),
            (right + clearance, center_y),
        ]
        candidates: list[tuple[float, float]] = []
        for candidate_x, candidate_y in raw_candidates:
            candidate_x = max(64.0, min(self.width - 64.0, candidate_x))
            candidate_y = max(64.0, min(self.height - 64.0, candidate_y))
            if self._is_static_walkable_point(candidate_x, candidate_y):
                candidates.append((candidate_x, candidate_y))
        candidates.sort(key=lambda point: distance(point[0], point[1], endpoint[0], endpoint[1]))
        return candidates

    def _path_still_crosses_obstacle(
        self,
        start: tuple[float, float],
        path: list[tuple[float, float]],
        obstacle: dict[str, Any],
    ) -> bool:
        rect = (
            float(obstacle["left"]),
            float(obstacle["top"]),
            float(obstacle["right"]),
            float(obstacle["bottom"]),
        )
        expanded = self._expand_rect(
            rect,
            STUDENT_COLLISION_WIDTH / 2.0 + STUDENT_COLLISION_PADDING,
            STUDENT_COLLISION_HEIGHT / 2.0 + STUDENT_COLLISION_PADDING,
        )
        previous = self._foot_point_from_position(start[0], start[1])
        for point_x, point_y in path:
            current = self._foot_point_from_position(point_x, point_y)
            if self._segment_intersects_rect(previous, current, expanded):
                return True
            previous = current
        return False

    def _is_entrance_release_step(self, student: Student, x: float, y: float) -> bool:
        if student.state != StudentState.MOVING_TO_QUEUE or x <= student.x:
            return False
        current_foot_x, current_foot_y = self._student_foot_point(student)
        next_foot_x, next_foot_y = self._foot_point_from_position(x, y)
        if current_foot_x > 96.0 or next_foot_x > 116.0:
            return False
        return any(
            abs(current_foot_y - entrance.y) <= entrance.height * 0.85
            or abs(next_foot_y - entrance.y) <= entrance.height * 0.85
            for entrance in self.entrances
        )

    def _try_local_avoidance_step(self, student: Student, step_distance: float) -> bool:
        if student.state in (StudentState.QUEUED, StudentState.EATING, StudentState.DONE):
            return False

        dx = student.target_x - student.x
        dy = student.target_y - student.y
        gap = (dx * dx + dy * dy) ** 0.5
        if gap < 1.0:
            dx, dy, gap = student.facing_x, student.facing_y, 1.0

        forward_x = dx / gap
        forward_y = dy / gap
        side_x = -forward_y
        side_y = forward_x
        side_step = max(LOCAL_AVOIDANCE_SIDE_STEP, step_distance * 1.25)
        forward_step = min(step_distance, 4.0)
        candidates: list[tuple[float, float]] = []
        for side in (1.0, -1.0):
            candidates.append(
                (
                    student.x + forward_x * forward_step + side_x * side * side_step,
                    student.y + forward_y * forward_step + side_y * side * side_step,
                )
            )
            candidates.append((student.x + side_x * side * side_step, student.y + side_y * side * side_step))
        candidates.sort(key=lambda point: distance(point[0], point[1], student.target_x, student.target_y))

        for candidate_x, candidate_y in candidates:
            if self._try_place_student_at(student, candidate_x, candidate_y):
                return True
        return False

    def _repair_unreachable_path_endpoint(self, student: Student) -> bool:
        if student.state in (StudentState.QUEUED, StudentState.EATING, StudentState.DONE):
            return False

        endpoint = student.path[-1] if student.path else (student.target_x, student.target_y)
        if distance(student.x, student.y, endpoint[0], endpoint[1]) <= 3.0:
            return False

        path, reachable_endpoint, endpoint_reachable = self._build_navigation_path_to_reachable_target(
            (student.x, student.y),
            endpoint,
            ignored_student_id=student.id,
        )
        if endpoint_reachable or not path:
            return False

        if distance(endpoint[0], endpoint[1], reachable_endpoint[0], reachable_endpoint[1]) <= 3.0:
            return False

        self._set_path(student, path)
        student.reroute_count += 1
        student.detour_until = self.game_time + 2.0
        student.local_avoidance_time = 0.0
        student.stuck_time = 0.0
        return True

    def _separate_students(self, game_delta: float) -> None:
        movable = self._collision_students()
        congestion_distance = 34.0
        crowded_ids: set[int] = set()
        for _ in range(4):
            resolved_overlap = False
            for first, second in self._nearby_student_pairs(movable):
                first_foot_x, first_foot_y = self._student_foot_point(first)
                second_foot_x, second_foot_y = self._student_foot_point(second)
                overlap = self._rects_overlap(
                    self._student_collision_rect(first),
                    self._student_collision_rect(second),
                )
                if overlap:
                    resolved_overlap = self._resolve_student_overlap(first, second) or resolved_overlap
                if overlap or distance(first_foot_x, first_foot_y, second_foot_x, second_foot_y) < congestion_distance:
                    crowded_ids.add(first.id)
                    crowded_ids.add(second.id)
            if not resolved_overlap:
                break

        for student in movable:
            if student.id in crowded_ids:
                student.congestion_time += game_delta * 0.45
            elif student.stuck_time >= 1.8:
                student.congestion_time += game_delta
            else:
                student.congestion_time = max(0.0, student.congestion_time - game_delta * 1.5)

            if student.stuck_time >= 1.6 and student.congestion_time >= 0.8:
                self._try_start_detour(student, movable)
                student.congestion_time = 0.0

    def _nearby_student_pairs(self, students: list[Student]) -> list[tuple[Student, Student]]:
        cell_size = 48.0
        grid: dict[tuple[int, int], list[Student]] = {}
        for student in students:
            foot_x, foot_y = self._student_foot_point(student)
            cell = (int(foot_x // cell_size), int(foot_y // cell_size))
            grid.setdefault(cell, []).append(student)

        pairs: list[tuple[Student, Student]] = []
        seen: set[tuple[int, int]] = set()
        for (cell_x, cell_y), bucket in grid.items():
            for d_x in (-1, 0, 1):
                for d_y in (-1, 0, 1):
                    neighbor_bucket = grid.get((cell_x + d_x, cell_y + d_y))
                    if not neighbor_bucket:
                        continue
                    for first in bucket:
                        for second in neighbor_bucket:
                            if first.id >= second.id:
                                continue
                            pair_key = (first.id, second.id)
                            if pair_key in seen:
                                continue
                            seen.add(pair_key)
                            pairs.append((first, second))
        return pairs

    def _resolve_student_overlap(self, first: Student, second: Student) -> bool:
        first_rect = self._student_collision_rect(first)
        second_rect = self._student_collision_rect(second)
        overlap_x = min(first_rect[2], second_rect[2]) - max(first_rect[0], second_rect[0])
        overlap_y = min(first_rect[3], second_rect[3]) - max(first_rect[1], second_rect[1])
        if overlap_x <= 0.0 or overlap_y <= 0.0:
            return False

        first_foot_x, first_foot_y = self._student_foot_point(first)
        second_foot_x, second_foot_y = self._student_foot_point(second)
        near_left_edge = first_foot_x < 92.0 and second_foot_x < 92.0
        if near_left_edge or overlap_x < overlap_y:
            sign = 1.0 if second_foot_x >= first_foot_x else -1.0
            offset_x = (overlap_x + STUDENT_COLLISION_PADDING) * sign
            offset_y = 0.0
        else:
            sign = 1.0 if second_foot_y >= first_foot_y else -1.0
            offset_x = 0.0
            offset_y = (overlap_y + STUDENT_COLLISION_PADDING) * sign

        first_weight, second_weight = self._separation_weights(first, second)
        total_weight = first_weight + second_weight
        if total_weight <= 0.0:
            return False

        first_share = first_weight / total_weight
        second_share = second_weight / total_weight
        moved = False
        if first_share > 0.0:
            moved = self._try_place_separated_student_at(
                first,
                first.x - offset_x * first_share,
                first.y - offset_y * first_share,
            ) or moved
        if second_share > 0.0:
            moved = self._try_place_separated_student_at(
                second,
                second.x + offset_x * second_share,
                second.y + offset_y * second_share,
            ) or moved
        return moved

    def _try_place_separated_student_at(self, student: Student, x: float, y: float) -> bool:
        x = max(28.0, min(self.width - 28.0, x))
        y = max(28.0, min(self.height - 28.0, y))
        if not self._is_static_walkable_point(x, y):
            return False
        if distance(student.x, student.y, x, y) <= 0.01:
            return False
        student.x = x
        student.y = y
        return True

    def _separation_weights(self, first: Student, second: Student) -> tuple[float, float]:
        first_weight = 0.35 if first.state == StudentState.QUEUED else 1.0
        second_weight = 0.35 if second.state == StudentState.QUEUED else 1.0
        if first.state == StudentState.QUEUED and second.state != StudentState.QUEUED:
            first_weight = 0.0
            second_weight = 1.0
        elif second.state == StudentState.QUEUED and first.state != StudentState.QUEUED:
            first_weight = 1.0
            second_weight = 0.0
        return first_weight, second_weight

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
            obstacle_width, obstacle_height = TABLE_OBSTACLE_SIZES.get(
                table.seat_count,
                TABLE_OBSTACLE_SIZES[4],
            )
            rects.append(
                {
                    "left": table.x - obstacle_width / 2.0,
                    "top": table.y - obstacle_height / 2.0,
                    "right": table.x + obstacle_width / 2.0,
                    "bottom": table.y + obstacle_height / 2.0,
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

        student.detour_until = self.game_time + 1.2
        original_path = list(student.path) if student.path else [(student.target_x, student.target_y)]
        candidate = self._find_detour_point(student, students)
        if candidate is not None and not self._path_crosses_static_blocking_obstacle(
            (student.x, student.y),
            [candidate],
            ignored_student_id=student.id,
        ):
            student.path = self._compact_path([candidate, *original_path])
            student.target_x, student.target_y = student.path[0]
            student.reroute_count += 1
            student.detour_until = self.game_time + 4.0
            student.stuck_time = 0.0
            return

        if self._reroute_student(student):
            student.reroute_count += 1
            student.detour_until = self.game_time + 3.0
            student.stuck_time = 0.0
            return

    def _reroute_student(self, student: Student) -> bool:
        if student.state == StudentState.MOVING_TO_QUEUE:
            before = list(student.path)
            self._start_queue_path(student, force=True)
            return bool(student.path) and student.path != before
        if student.state == StudentState.MOVING_TO_SEAT and student.table_id is not None and student.seat_index is not None:
            table = self.tables[student.table_id]
            seat_x, seat_y = self._seat_position(table, student.seat_index)
            path = self._build_table_path(student.x, student.y, table, student.seat_index, seat_x, seat_y)
            self._set_path(student, path)
            return bool(student.path)
        if student.state == StudentState.MOVING_TO_TRAY_RETURN:
            self._set_tray_return_path(student, force=True)
            return bool(student.path)
        if student.state == StudentState.LEAVING:
            self._set_exit_path(student, force=True)
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
            for forward_step in (0.0, 36.0, 72.0):
                for side_step in (34.0, 54.0, 78.0, 102.0):
                    candidates.append(
                        (
                            student.x + forward_x * forward_step + nx * side * side_step,
                            student.y + forward_y * forward_step + ny * side * side_step,
                        )
                    )

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
            if (
                left - STUDENT_COLLISION_FOOT_OFFSET_Y <= foot_x <= right + STUDENT_COLLISION_FOOT_OFFSET_Y
                and top - STUDENT_COLLISION_FOOT_OFFSET_Y <= foot_y <= bottom + STUDENT_COLLISION_FOOT_OFFSET_Y
            ):
                return False
        candidate_rect = self._student_collision_rect_from_position(x, y)
        for other in students:
            if other.id == ignored_student_id:
                continue
            if not self._student_uses_collision_box(other):
                continue
            if self._rects_overlap(candidate_rect, self._student_collision_rect(other), STUDENT_COLLISION_PADDING):
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
            if (
                item["left"] - STUDENT_COLLISION_FOOT_OFFSET_Y <= foot_x <= item["right"] + STUDENT_COLLISION_FOOT_OFFSET_Y
                and item["top"] - STUDENT_COLLISION_FOOT_OFFSET_Y <= foot_y <= item["bottom"] + STUDENT_COLLISION_FOOT_OFFSET_Y
            ):
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
        moving = [student for student in active if self._student_needs_navigation_work(student)]
        avg_move_speed = _average_float(student.actual_speed for student in moving) if moving else None
        density_load = sum(
            max(0, self._neighbor_count(*self._student_foot_point(student), 58.0, student.id) - 1)
            for student in moving
        )
        congestion_index = min(1.0, density_load / max(1.0, len(moving) * 3.0)) if moving else 0.0
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

    def _student_needs_navigation_work(self, student: Student) -> bool:
        return student.state not in (StudentState.EATING, StudentState.QUEUED, StudentState.DONE)

    def _build_frame(
        self,
        *,
        lightweight_students: bool = False,
        include_student_details: bool = False,
    ) -> dict[str, Any]:
        stats = self.data_recorder.build_stats(current_time=self.game_time).to_dict()
        issues = [*self.issues, *self.data_recorder.issues]
        walk_paths = self._build_walk_paths()
        active_students = [
            student
            for student in self.students.values()
            if student.state != StudentState.DONE
        ]
        frame = {
            "game_time": min(self.game_time, self._hard_stop_game_time()),
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
            "walk_paths": walk_paths,
            "path_debug_lines": walk_paths,
            "obstacles": self._obstacle_frames(),
            "collision_boxes": self._build_collision_boxes(),
            "stalls": [self._stall_frame(stall) for stall in self.stalls],
            "tables": [self._table_frame(table) for table in self.tables],
            "students": [
                self._student_render_frame(student) if lightweight_students else self._student_frame(student)
                for student in active_students
            ],
        }
        if include_student_details:
            frame["student_details"] = [
                self._student_frame(student)
                for student in active_students
            ]
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

    def _table_frame(self, table: Table) -> dict[str, Any]:
        seat_frames = [
            self._table_seat_frame(table, seat_index, seat)
            for seat_index, seat in enumerate(table.seats)
        ]
        occupied_count = sum(1 for seat in table.seats if seat.status == SeatStatus.OCCUPIED)
        reserved_count = sum(1 for seat in table.seats if seat.status == SeatStatus.RESERVED)
        free_count = max(0, table.seat_count - occupied_count - reserved_count)
        return {
            "id": table.id,
            "x": table.x,
            "y": table.y,
            "table_type": table.table_type,
            "seat_count": table.seat_count,
            "occupied": occupied_count,
            "occupied_count": occupied_count,
            "reserved_count": reserved_count,
            "free_count": free_count,
            "occupancy_rate": occupied_count / max(1, table.seat_count),
            "seats": [seat.student_id for seat in table.seats],
            "seat_frames": seat_frames,
            "companion_groups": self._table_companion_groups(seat_frames),
        }

    def _table_seat_frame(self, table: Table, seat_index: int, seat: Any) -> dict[str, Any]:
        student = self.students.get(seat.student_id) if seat.student_id is not None else None
        frame = {
            "index": seat_index,
            "status": seat.status.value if isinstance(seat.status, SeatStatus) else str(seat.status),
            "student_id": seat.student_id,
        }
        if student is not None:
            frame["student"] = self._table_student_frame(student)
        return frame

    def _table_student_frame(self, student: Student) -> dict[str, Any]:
        eating_metrics = self._student_eating_metrics(student)
        companion_ids = [
            member.id
            for member in self.students.values()
            if member.id != student.id
            and member.group_id is not None
            and member.group_id == student.group_id
            and member.table_id == student.table_id
            and member.state != StudentState.DONE
        ]
        return {
            "id": student.id,
            "state": student.state.value if isinstance(student.state, StudentState) else str(student.state),
            "group_id": student.group_id,
            "group_size": student.group_size,
            "seat_index": student.seat_index,
            "dish_id": student.dish_id,
            "order_id": student.order_id,
            "eating_duration": eating_metrics["duration"],
            "eating_elapsed": eating_metrics["elapsed"],
            "eating_remaining": eating_metrics["remaining"],
            "eating_progress": eating_metrics["progress"],
            "companion_ids": sorted(companion_ids),
        }

    def _table_companion_groups(self, seat_frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[int, dict[str, Any]] = {}
        for seat in seat_frames:
            student = seat.get("student")
            if not isinstance(student, dict):
                continue
            group_id = student.get("group_id")
            group_size = student.get("group_size")
            if group_id is None or not isinstance(group_size, int) or group_size <= 1:
                continue
            group = groups.setdefault(
                int(group_id),
                {
                    "group_id": int(group_id),
                    "group_size": group_size,
                    "members": [],
                },
            )
            group["group_size"] = max(int(group["group_size"]), group_size)
            group["members"].append(
                {
                    "student_id": student.get("id"),
                    "seat_index": seat.get("index"),
                    "state": student.get("state"),
                    "eating_progress": student.get("eating_progress"),
                }
            )

        companion_groups = []
        for group in groups.values():
            members = sorted(
                group["members"],
                key=lambda item: (
                    item.get("seat_index") if item.get("seat_index") is not None else 999,
                    item.get("student_id") if item.get("student_id") is not None else 999,
                ),
            )
            companion_groups.append(
                {
                    "group_id": group["group_id"],
                    "group_size": group["group_size"],
                    "member_ids": [member.get("student_id") for member in members],
                    "members": members,
                }
            )
        return sorted(companion_groups, key=lambda group: group["group_id"])

    def _stall_frame(self, stall: Stall) -> dict[str, Any]:
        dishes = stall.dishes or []
        orders = stall.orders or []
        queue_count = len(stall.queue or [])
        return {
            "id": stall.id,
            "name": stall.name or "",
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
        estimated_finished_at = order.finished_at
        remaining = (
            max(0.0, estimated_finished_at - self.game_time)
            if estimated_finished_at is not None and status != OrderStatus.DONE.value
            else 0.0
        )
        progress = 1.0 if status == OrderStatus.DONE.value else 0.0
        if order.started_at is not None and estimated_finished_at is not None:
            total = max(0.001, estimated_finished_at - order.started_at)
            progress = max(0.0, min(1.0, (self.game_time - order.started_at) / total))
        return {
            "id": order.id,
            "student_id": order.student_id,
            "stall_id": order.stall_id,
            "dish_id": order.dish_id,
            "created_at": float(order.created_at),
            "started_at": order.started_at,
            "finished_at": order.finished_at if status == OrderStatus.DONE.value else None,
            "estimated_finished_at": estimated_finished_at,
            "remaining": remaining,
            "progress": progress,
            "status": status,
        }

    def _student_render_frame(self, student: Student) -> dict[str, Any]:
        return {
            "id": student.id,
            "x": student.x,
            "y": student.y,
            "state": student.state.value if isinstance(student.state, StudentState) else str(student.state),
            "stall_id": student.stall_id,
            "order_id": student.order_id,
            "dish_id": student.dish_id,
            "group_id": student.group_id,
            "group_size": student.group_size,
            "table_id": student.table_id,
            "seat_index": student.seat_index,
            "facing_x": student.facing_x,
            "facing_y": student.facing_y,
            "stuck_time": student.stuck_time,
        }

    def _student_frame(self, student: Student) -> dict[str, Any]:
        eating_metrics = self._student_eating_metrics(student)
        path_metrics = self._student_path_metrics(student)
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
            "dish_name": self._student_dish_name(student),
            "order_id": student.order_id,
            "group_id": student.group_id,
            "group_size": student.group_size,
            "entrance_id": student.entrance_id,
            "exit_id": student.exit_id,
            "stall_id": student.stall_id,
            "queue_position": self._student_queue_position(student),
            "table_id": student.table_id,
            "seat_index": student.seat_index,
            "time_in_system": max(0.0, self.game_time - student.spawn_time),
            "decision_remaining": (
                max(0.0, student.decision_done_at - self.game_time)
                if student.state == StudentState.DECIDING
                else None
            ),
            "waiting_seat_time": (
                max(0.0, self.game_time - student.waiting_seat_since)
                if student.waiting_seat_since is not None
                else None
            ),
            "actual_speed": student.actual_speed,
            "stuck_time": student.stuck_time,
            "reroute_count": student.reroute_count,
            "path_id": student.path_id,
            "path_started_at": student.path_started_at,
            "path_duration": path_metrics["duration"],
            "path_length": student.path_length,
            "path_remaining_distance": path_metrics["remaining_distance"],
            "path_progress": path_metrics["progress"],
            "path_waypoint_count": len(student.path or []),
            "path_status": path_metrics["status"],
            "facing_x": student.facing_x,
            "facing_y": student.facing_y,
            "eating_duration": eating_metrics["duration"],
            "eating_elapsed": eating_metrics["elapsed"],
            "eating_remaining": eating_metrics["remaining"],
            "eating_progress": eating_metrics["progress"],
        }

    def _student_eating_metrics(self, student: Student) -> dict[str, float | None]:
        duration = max(0.001, float(student.eating_time))
        if student.state != StudentState.EATING or student.eating_done_at is None:
            return {
                "duration": duration,
                "elapsed": None,
                "remaining": None,
                "progress": None,
            }

        remaining = max(0.0, student.eating_done_at - self.game_time)
        elapsed = max(0.0, min(duration, duration - remaining))
        progress = max(0.0, min(1.0, elapsed / duration))
        return {
            "duration": duration,
            "elapsed": elapsed,
            "remaining": remaining,
            "progress": progress,
        }

    def _student_path_metrics(self, student: Student) -> dict[str, float | str | None]:
        remaining_distance = self._student_path_remaining_distance(student)
        path_duration = (
            max(0.0, self.game_time - student.path_started_at)
            if student.path_started_at is not None
            else None
        )
        progress = None
        if student.path_length is not None and student.path_length > 0 and remaining_distance is not None:
            progress = clamp(1.0 - remaining_distance / student.path_length, 0.0, 1.0)

        if student.path_id is not None:
            status = "active"
        elif student.path:
            status = "pending"
        elif self._student_needs_navigation_work(student) and distance(student.x, student.y, student.target_x, student.target_y) > 4.0:
            status = "direct"
        else:
            status = "idle"

        return {
            "status": status,
            "duration": path_duration,
            "remaining_distance": remaining_distance,
            "progress": progress,
        }

    def _student_path_remaining_distance(self, student: Student) -> float | None:
        if student.path:
            return self._path_distance(student.x, student.y, list(student.path or []))
        if self._student_needs_navigation_work(student):
            return distance(student.x, student.y, student.target_x, student.target_y)
        return None

    def _student_queue_position(self, student: Student) -> int | None:
        if student.stall_id is None or student.stall_id < 0 or student.stall_id >= len(self.stalls):
            return None
        stall = self.stalls[student.stall_id]
        if student.id in stall.queue:
            return stall.queue.index(student.id) + 1
        if student.state == StudentState.MOVING_TO_QUEUE:
            return len(stall.queue) + self._inbound_queue_rank(student) + 1
        return None

    def _student_dish_name(self, student: Student) -> str | None:
        if student.dish_id is None:
            return None
        for stall in self.stalls:
            dish = self._dish_by_id(stall, student.dish_id)
            if dish is not None:
                return dish.name
        return None

    def _stall_cook_remaining(self, stall: Stall) -> float:
        if not stall.ready_times:
            return 0.0
        return max(0.0, stall.ready_times[0][1] - self.game_time)

    def _stall_cook_progress(self, stall: Stall) -> float:
        if not stall.ready_times:
            return 0.0
        cook_time = stall.cook_time
        if cook_time <= 0:
            return 0.0
        remaining = self._stall_cook_remaining(stall)
        return max(0.0, min(1.0, 1.0 - remaining / cook_time))

    def _build_collision_boxes(self) -> list[dict[str, Any]]:
        boxes: list[dict[str, Any]] = []
        for left, top, right, bottom in self._obstacle_rects():
            boxes.append(
                {
                    "x": (left + right) / 2.0,
                    "y": (top + bottom) / 2.0,
                    "width": right - left,
                    "height": bottom - top,
                    "kind": "static",
                }
            )
        for student in self._collision_students():
            left, top, right, bottom = self._student_collision_rect(student)
            boxes.append(
                {
                    "x": (left + right) / 2.0,
                    "y": (top + bottom) / 2.0,
                    "width": right - left,
                    "height": bottom - top,
                    "kind": "student",
                    "student_id": student.id,
                    "state": student.state.value if isinstance(student.state, StudentState) else str(student.state),
                }
            )
        return boxes

    def _build_walk_paths(self) -> list[dict[str, Any]]:
        if self._walk_paths_cache is not None:
            return self._walk_paths_cache

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
        self._walk_paths_cache = paths
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
        dishes_per_stall = max(1, int(raw.get("dishes_per_stall", 3)))
        price_jitter = _two_float_tuple(raw.get("price_jitter"), (-0.5, 0.8))
        cook_time_jitter = _two_float_tuple(raw.get("cook_time_jitter"), (-2.0, 3.0))

        windows = raw.get("windows")
        if isinstance(windows, list) and windows:
            # New window-based menu structure
            normalized_windows: list[dict[str, Any]] = []
            for win in windows:
                if not isinstance(win, dict):
                    raise ValueError("each window must be an object")
                win_name = str(win.get("name", ""))
                win_dishes_raw = win.get("dishes")
                if not isinstance(win_dishes_raw, list) or not win_dishes_raw:
                    raise ValueError(f"window '{win_name}' dishes must be a non-empty list")
                normalized_win_dishes: list[dict[str, Any]] = []
                for dish in win_dishes_raw:
                    if not isinstance(dish, dict):
                        raise ValueError(f"dish in window '{win_name}' must be an object")
                    features = dish.get("features")
                    if not isinstance(features, dict):
                        raise ValueError(f"dish {dish.get('id')} in window '{win_name}' missing features")
                    normalized_win_dishes.append({
                        "id": int(dish["id"]),
                        "name": str(dish["name"]),
                        "features": {str(key): float(value) for key, value in features.items()},
                        "price": float(dish["price"]),
                        "stock": max(0, int(dish["stock"])),
                        "cook_time": max(1.0, float(dish["cook_time"])),
                    })
                normalized_windows.append({
                    "name": win_name,
                    "dishes": normalized_win_dishes,
                })
            return {
                "dishes_per_stall": dishes_per_stall,
                "price_jitter": price_jitter,
                "cook_time_jitter": cook_time_jitter,
                "windows": normalized_windows,
                "dishes": [],  # placeholder for backward compat
            }, issues
        else:
            # Legacy flat dish list
            dishes = raw.get("dishes")
            if not isinstance(dishes, list) or not dishes:
                raise ValueError("dishes must be a non-empty list")
            normalized_dishes: list[dict[str, Any]] = []
            for index, dish in enumerate(dishes):
                if not isinstance(dish, dict):
                    raise ValueError(f"dish {index} must be an object")
                features = dish.get("features")
                if not isinstance(features, dict):
                    raise ValueError(f"dish {index} missing features")
                normalized_dishes.append({
                    "id": int(dish["id"]),
                    "name": str(dish["name"]),
                    "features": {str(key): float(value) for key, value in features.items()},
                    "price": float(dish["price"]),
                    "stock": max(0, int(dish["stock"])),
                    "cook_time": max(1.0, float(dish["cook_time"])),
                })
            return {
                "dishes_per_stall": dishes_per_stall,
                "price_jitter": price_jitter,
                "cook_time_jitter": cook_time_jitter,
                "windows": [],
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
        "dishes_per_stall": 4,
        "price_jitter": (-0.5, 0.8),
        "cook_time_jitter": (-2.0, 3.0),
        "windows": [
            {
                "name": "川湘风味",
                "dishes": [
                    {"id": 101, "name": "麻辣香锅", "features": {"meat": 0.65, "veg": 0.45, "spicy": 0.95}, "price": 16.0, "stock": 24, "cook_time": 25.0},
                    {"id": 102, "name": "回锅肉盖饭", "features": {"meat": 0.78, "veg": 0.32, "spicy": 0.80}, "price": 14.0, "stock": 24, "cook_time": 22.0},
                    {"id": 103, "name": "酸菜鱼", "features": {"meat": 0.60, "veg": 0.50, "spicy": 0.70}, "price": 17.0, "stock": 20, "cook_time": 28.0},
                    {"id": 104, "name": "麻婆豆腐饭", "features": {"meat": 0.20, "veg": 0.85, "spicy": 0.88}, "price": 11.0, "stock": 30, "cook_time": 15.0},
                    {"id": 105, "name": "干锅花菜", "features": {"meat": 0.15, "veg": 0.90, "spicy": 0.65}, "price": 10.0, "stock": 28, "cook_time": 18.0},
                ],
            },
            {
                "name": "粤式烧腊",
                "dishes": [
                    {"id": 201, "name": "蜜汁叉烧饭", "features": {"meat": 0.85, "veg": 0.25, "spicy": 0.05}, "price": 15.0, "stock": 24, "cook_time": 20.0},
                    {"id": 202, "name": "烧鸭饭", "features": {"meat": 0.82, "veg": 0.28, "spicy": 0.08}, "price": 16.0, "stock": 22, "cook_time": 22.0},
                    {"id": 203, "name": "白切鸡饭", "features": {"meat": 0.80, "veg": 0.30, "spicy": 0.02}, "price": 14.0, "stock": 24, "cook_time": 18.0},
                    {"id": 204, "name": "腊味煲仔饭", "features": {"meat": 0.75, "veg": 0.35, "spicy": 0.10}, "price": 18.0, "stock": 18, "cook_time": 30.0},
                    {"id": 205, "name": "卤水拼盘", "features": {"meat": 0.70, "veg": 0.40, "spicy": 0.15}, "price": 13.0, "stock": 20, "cook_time": 16.0},
                ],
            },
            {
                "name": "西北面食",
                "dishes": [
                    {"id": 301, "name": "兰州拉面", "features": {"meat": 0.55, "veg": 0.55, "spicy": 0.20}, "price": 12.0, "stock": 30, "cook_time": 14.0},
                    {"id": 302, "name": "油泼扯面", "features": {"meat": 0.10, "veg": 0.90, "spicy": 0.60}, "price": 10.0, "stock": 30, "cook_time": 12.0},
                    {"id": 303, "name": "羊肉泡馍", "features": {"meat": 0.70, "veg": 0.40, "spicy": 0.30}, "price": 17.0, "stock": 20, "cook_time": 26.0},
                    {"id": 304, "name": "岐山臊子面", "features": {"meat": 0.45, "veg": 0.60, "spicy": 0.50}, "price": 11.0, "stock": 28, "cook_time": 14.0},
                    {"id": 305, "name": "肉夹馍套餐", "features": {"meat": 0.72, "veg": 0.38, "spicy": 0.15}, "price": 13.0, "stock": 24, "cook_time": 16.0},
                ],
            },
            {
                "name": "家常套餐",
                "dishes": [
                    {"id": 1401, "name": "红烧肉饭", "features": {"meat": 0.82, "veg": 0.28, "spicy": 0.15}, "price": 14.0, "stock": 24, "cook_time": 24.0},
                    {"id": 1402, "name": "番茄炒蛋饭", "features": {"meat": 0.15, "veg": 0.88, "spicy": 0.02}, "price": 9.0, "stock": 30, "cook_time": 12.0},
                    {"id": 1403, "name": "土豆炖牛肉", "features": {"meat": 0.68, "veg": 0.42, "spicy": 0.20}, "price": 16.0, "stock": 22, "cook_time": 28.0},
                    {"id": 1404, "name": "清蒸鲈鱼", "features": {"meat": 0.72, "veg": 0.38, "spicy": 0.05}, "price": 18.0, "stock": 16, "cook_time": 24.0},
                    {"id": 1405, "name": "青椒肉丝", "features": {"meat": 0.60, "veg": 0.50, "spicy": 0.35}, "price": 12.0, "stock": 26, "cook_time": 14.0},
                ],
            },
        ],
        "dishes": [],
    }
