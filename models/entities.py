from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StudentState(str, Enum):
    DECIDING = "deciding"
    MOVING_TO_QUEUE = "moving_to_queue"
    QUEUED = "queued"
    SEARCHING_SEAT = "searching_seat"
    WAITING_SEAT = "waiting_seat"
    MOVING_TO_SEAT = "moving_to_seat"
    EATING = "eating"
    MOVING_TO_TRAY_RETURN = "moving_to_tray_return"
    LEAVING = "leaving"
    DONE = "done"


class StallStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    SOLD_OUT = "sold_out"


class OrderStatus(str, Enum):
    QUEUED = "queued"
    COOKING = "cooking"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class SimulationConfig:
    sim_minutes: int = 30
    time_scale: float = 6.0
    stall_count: int = 10
    table_count: int = 24
    two_person_table_count: int | None = None
    four_person_table_count: int | None = None
    six_person_table_count: int | None = None
    dish_preference_weight: float = 0.4
    price_weight: float = 0.2
    default_dish_stock: int = 24
    low_stock_threshold: int = 3
    companion_ratio: float = 0.25
    entrance_count: int = 1
    exit_count: int = 1
    show_path_debug_layer: bool = False
    show_obstacle_layer: bool = False
    seed: int | None = None
    total_student_count: int = 120
    max_active_students: int = 120
    companion_pair_ratio: float = 0.18
    companion_multi_ratio: float = 0.08
    entrance_weights: tuple[float, ...] = (1.0, 0.7, 0.5)

    @property
    def duration_game_seconds(self) -> float:
        return float(self.sim_minutes * 60)

    @property
    def duration_real_seconds(self) -> float:
        return self.duration_game_seconds / self.time_scale

    def resolved_table_type_counts(self) -> dict[str, int]:
        explicit_counts = {
            "two": self.two_person_table_count,
            "four": self.four_person_table_count,
            "six": self.six_person_table_count,
        }
        if any(value is not None for value in explicit_counts.values()):
            return {
                table_type: max(0, int(value or 0))
                for table_type, value in explicit_counts.items()
            }

        count = max(1, int(self.table_count))
        if count == 1:
            return {"two": 0, "four": 1, "six": 0}
        two_count = max(1, count // 4)
        six_count = max(0, count // 4)
        four_count = max(0, count - two_count - six_count)
        return {"two": two_count, "four": four_count, "six": six_count}


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
    preferences: dict[str, float] = field(default_factory=dict)
    dish_id: int | None = None
    order_id: int | None = None
    group_id: int | None = None
    group_size: int | None = None
    entrance_id: int | None = None
    exit_id: int | None = None
    decision_done_at: float = 0.0
    food_ready_at: float | None = None
    eating_done_at: float | None = None
    eating_duration: float | None = None
    walk_speed: float = 14.0
    table_walk_speed: float = 12.0
    path: list[tuple[float, float]] = field(default_factory=list)
    congestion_time: float = 0.0
    detour_until: float = 0.0
    actual_speed: float = 0.0
    stuck_time: float = 0.0
    local_avoidance_time: float = 0.0
    reroute_count: int = 0
    facing_x: float = 1.0
    facing_y: float = 0.0
    waiting_seat_since: float | None = None
    path_id: str | None = None
    path_started_at: float | None = None
    path_length: float | None = None
    last_x: float = field(init=False)
    last_y: float = field(init=False)

    def __post_init__(self) -> None:
        self.last_x = self.x
        self.last_y = self.y

    @property
    def eating_time(self) -> float:
        if self.eating_duration is not None:
            return self.eating_duration
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
    ready_times: list[tuple[int, float, int]] = field(default_factory=list)
    next_food_ready_time: float = 0.0
    status: StallStatus = StallStatus.PENDING
    dishes: list["Dish"] = field(default_factory=list)
    orders: list["Order"] = field(default_factory=list)

    def available_dishes(self) -> list["Dish"]:
        return [dish for dish in self.dishes if dish.available]

    def refresh_status(self) -> None:
        self.status = StallStatus.OPEN if self.available_dishes() else StallStatus.SOLD_OUT


@dataclass
class Dish:
    id: int
    name: str
    features: dict[str, float]
    price: float
    stock: int
    cook_time: float

    @property
    def available(self) -> bool:
        return self.stock > 0


@dataclass(frozen=True)
class Entrance:
    id: int
    x: float
    y: float
    width: float
    height: float
    weight: float


@dataclass(frozen=True)
class Exit:
    id: int
    x: float
    y: float
    width: float
    height: float


@dataclass
class Order:
    id: int
    student_id: int
    stall_id: int
    dish_id: int
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    status: OrderStatus = OrderStatus.QUEUED


class SeatStatus(str, Enum):
    FREE = "free"
    RESERVED = "reserved"
    OCCUPIED = "occupied"


@dataclass
class Seat:
    status: SeatStatus = SeatStatus.FREE
    student_id: int | None = None


@dataclass
class Table:
    id: int
    x: float
    y: float
    table_type: str = "four"
    seat_count: int = 4
    seats: list[Seat] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.seat_count = max(1, int(self.seat_count))
        if not self.seats:
            self.seats = [Seat() for _ in range(self.seat_count)]

    def free_seat_indexes(self) -> list[int]:
        return [
            index
            for index, seat in enumerate(self.seats)
            if seat.status == SeatStatus.FREE and seat.student_id is None
        ]

    @property
    def occupied_count(self) -> int:
        return sum(1 for seat in self.seats if seat.status == SeatStatus.OCCUPIED)


@dataclass(frozen=True)
class RunSummary:
    status: str
    game_time: float
    spawned_students: int
    finished_eating_students: int
    active_students: int

    @property
    def served_students(self) -> int:
        return self.finished_eating_students
