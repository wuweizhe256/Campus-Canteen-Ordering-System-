from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StudentState(str, Enum):
    DECIDING = "deciding"
    MOVING_TO_QUEUE = "moving_to_queue"
    QUEUED = "queued"
    WAITING_SEAT = "waiting_seat"
    MOVING_TO_TABLE = "moving_to_table"
    EATING = "eating"
    LEAVING = "leaving"
    DONE = "done"


@dataclass(frozen=True)
class SimulationConfig:
    sim_minutes: int = 30
    time_scale: float = 6.0
    stall_count: int = 10
    table_count: int = 24
    seed: int | None = None
    total_student_count: int = 120
    max_active_students: int = 55

    @property
    def duration_game_seconds(self) -> float:
        return float(self.sim_minutes * 60)

    @property
    def duration_real_seconds(self) -> float:
        return self.duration_game_seconds / self.time_scale


@dataclass
class Student:
    id: int
    meat_pref: float
    veg_pref: float
    appetite: float
    eat_speed: float
    hesitation_time: float
    table_walk_time: float
    spawn_time: float
    x: float
    y: float
    target_x: float
    target_y: float
    state: StudentState = StudentState.DECIDING
    stall_id: int | None = None
    table_id: int | None = None
    seat_index: int | None = None
    decision_done_at: float = 0.0
    food_ready_at: float | None = None
    eating_done_at: float | None = None
    walk_speed: float = 14.0
    table_walk_speed: float = 12.0
    path: list[tuple[float, float]] = field(default_factory=list)
    congestion_time: float = 0.0
    detour_until: float = 0.0

    @property
    def eating_time(self) -> float:
        return self.appetite / self.eat_speed


@dataclass
class Stall:
    id: int
    x: float
    y: float
    meat_ratio: float
    veg_ratio: float
    cook_time: float
    queue: list[int] = field(default_factory=list)
    ready_times: list[tuple[int, float]] = field(default_factory=list)
    next_food_ready_time: float = 0.0


@dataclass
class Table:
    id: int
    x: float
    y: float
    seats: list[int | None] = field(default_factory=lambda: [None, None, None, None])

    def free_seat_indexes(self) -> list[int]:
        return [index for index, occupant in enumerate(self.seats) if occupant is None]

    @property
    def occupied_count(self) -> int:
        return sum(1 for occupant in self.seats if occupant is not None)


@dataclass(frozen=True)
class RunSummary:
    status: str
    game_time: float
    spawned_students: int
    served_students: int
    active_students: int
