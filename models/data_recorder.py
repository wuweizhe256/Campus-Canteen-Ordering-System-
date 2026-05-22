from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable


P0_EVENT_TYPES = {
    "student_spawned",
    "queue_started",
    "food_ready",
    "eating_started",
    "eating_finished",
    "student_left",
}

P1_EVENT_TYPES = {
    "order_created",
    "order_started",
    "order_completed",
    "order_cancelled",
    "dish_stock_changed",
    "dish_sold_out",
}

P2_EVENT_TYPES = {
    "group_created",
    "group_member_joined",
    "seat_assigned",
    "seat_released",
    "table_type_registered",
}

EVENT_TYPES = P0_EVENT_TYPES | P1_EVENT_TYPES | P2_EVENT_TYPES


@dataclass(frozen=True)
class EventRecordP0:
    event_type: str
    game_time: float
    student_id: int | None = None
    stall_id: int | None = None
    dish_id: int | None = None
    order_id: int | None = None
    group_id: int | None = None
    group_size: int | None = None
    table_id: int | None = None
    seat_index: int | None = None
    table_type: str | None = None
    seat_count: int | None = None
    quantity: int | None = None
    price: float | None = None
    stock_before: int | None = None
    stock_after: int | None = None
    order_status: str | None = None
    stall_status: str | None = None
    from_state: str | None = None
    to_state: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "EventRecordP0":
        return cls(
            event_type=str(value["event_type"]),
            game_time=float(value["game_time"]),
            student_id=_optional_int(value.get("student_id")),
            stall_id=_optional_int(value.get("stall_id")),
            dish_id=_optional_int(value.get("dish_id")),
            order_id=_optional_int(value.get("order_id")),
            group_id=_optional_int(value.get("group_id")),
            group_size=_optional_int(value.get("group_size")),
            table_id=_optional_int(value.get("table_id")),
            seat_index=_optional_int(value.get("seat_index")),
            table_type=_optional_str(value.get("table_type")),
            seat_count=_optional_int(value.get("seat_count")),
            quantity=_optional_int(value.get("quantity")),
            price=_optional_float(value.get("price")),
            stock_before=_optional_int(value.get("stock_before")),
            stock_after=_optional_int(value.get("stock_after")),
            order_status=_optional_str(value.get("order_status")),
            stall_status=_optional_str(value.get("stall_status")),
            from_state=_optional_str(value.get("from_state")),
            to_state=_optional_str(value.get("to_state")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StallQueueStats:
    stall_id: int
    max_queue_length: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class DishSalesStats:
    dish_id: int
    stall_id: int | None
    sales_count: int
    revenue: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DishSoldOutStats:
    dish_id: int
    stall_id: int | None
    sold_out_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DishStockStats:
    dish_id: int
    stall_id: int | None
    stock: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StatsFrameP0:
    avg_wait_time: float | None
    avg_total_time: float | None
    max_active_students: int
    stall_queue_stats: list[StallQueueStats]
    seat_utilization: float | None
    avg_move_speed: float | None
    congestion_index: float
    stuck_student_count: int
    reroute_count: int
    avg_queue_length: float | None
    tray_return_queue_length: int
    dish_sales_stats: list[DishSalesStats]
    dish_sold_out_stats: list[DishSoldOutStats]
    dish_stock_stats: list[DishStockStats]
    avg_order_wait_time: float | None
    avg_order_cook_time: float | None
    avg_order_total_time: float | None
    completed_order_count: int
    cancelled_order_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "avg_wait_time": self.avg_wait_time,
            "avg_total_time": self.avg_total_time,
            "max_active_students": self.max_active_students,
            "stall_queue_stats": [item.to_dict() for item in self.stall_queue_stats],
            "seat_utilization": self.seat_utilization,
            "avg_move_speed": self.avg_move_speed,
            "congestion_index": self.congestion_index,
            "stuck_student_count": self.stuck_student_count,
            "reroute_count": self.reroute_count,
            "avg_queue_length": self.avg_queue_length,
            "tray_return_queue_length": self.tray_return_queue_length,
            "dish_sales_stats": [item.to_dict() for item in self.dish_sales_stats],
            "dish_sold_out_stats": [item.to_dict() for item in self.dish_sold_out_stats],
            "dish_stock_stats": [item.to_dict() for item in self.dish_stock_stats],
            "avg_order_wait_time": self.avg_order_wait_time,
            "avg_order_cook_time": self.avg_order_cook_time,
            "avg_order_total_time": self.avg_order_total_time,
            "completed_order_count": self.completed_order_count,
            "cancelled_order_count": self.cancelled_order_count,
        }


@dataclass(frozen=True)
class RuntimeStatsSample:
    game_time: float
    avg_move_speed: float | None
    congestion_index: float
    stuck_student_count: int
    reroute_count: int
    avg_queue_length: float | None
    tray_return_queue_length: int


@dataclass(frozen=True)
class QueueLengthSample:
    game_time: float
    stall_id: int
    queue_length: int


class DataRecorder:
    def __init__(self, total_seats: int | None = None, duration: float | None = None) -> None:
        self.total_seats = total_seats
        self.duration = duration
        self.events: list[EventRecordP0] = []
        self.events_by_student: dict[int, list[EventRecordP0]] = defaultdict(list)
        self.events_by_stall: dict[int, list[EventRecordP0]] = defaultdict(list)
        self.events_by_dish: dict[int, list[EventRecordP0]] = defaultdict(list)
        self.events_by_order: dict[int, list[EventRecordP0]] = defaultdict(list)
        self.events_by_group: dict[int, list[EventRecordP0]] = defaultdict(list)
        self.events_by_table_type: dict[str, list[EventRecordP0]] = defaultdict(list)
        self.events_by_seat: dict[tuple[int, int], list[EventRecordP0]] = defaultdict(list)
        self.queue_samples: list[QueueLengthSample] = []
        self.runtime_samples: list[RuntimeStatsSample] = []
        self.issues: list[str] = []

    def record_event(self, event: EventRecordP0 | dict[str, Any]) -> None:
        record = EventRecordP0.from_mapping(event) if isinstance(event, dict) else event
        if record.event_type not in EVENT_TYPES:
            self.issues.append(f"unknown event_type: {record.event_type}")
            return

        self.events.append(record)
        if record.student_id is not None:
            self.events_by_student[record.student_id].append(record)
        if record.stall_id is not None:
            self.events_by_stall[record.stall_id].append(record)
        if record.dish_id is not None:
            self.events_by_dish[record.dish_id].append(record)
        if record.order_id is not None:
            self.events_by_order[record.order_id].append(record)
        if record.group_id is not None:
            self.events_by_group[record.group_id].append(record)
        if record.table_type is not None:
            self.events_by_table_type[record.table_type].append(record)
        if record.table_id is not None and record.seat_index is not None:
            self.events_by_seat[(record.table_id, record.seat_index)].append(record)

    def feed_event(self, event: EventRecordP0 | dict[str, Any]) -> None:
        self.record_event(event)

    def record_queue_sample(self, game_time: float, stall_id: int, queue_length: int) -> None:
        self.queue_samples.append(
            QueueLengthSample(
                game_time=float(game_time),
                stall_id=int(stall_id),
                queue_length=max(0, int(queue_length)),
            )
        )

    def feed_queue_sample(self, game_time: float, stall_id: int, queue_length: int) -> None:
        self.record_queue_sample(game_time, stall_id, queue_length)

    def record_runtime_sample(
        self,
        game_time: float,
        avg_move_speed: float | None,
        congestion_index: float,
        stuck_student_count: int,
        reroute_count: int,
        avg_queue_length: float | None,
        tray_return_queue_length: int,
    ) -> None:
        self.runtime_samples.append(
            RuntimeStatsSample(
                game_time=float(game_time),
                avg_move_speed=avg_move_speed,
                congestion_index=max(0.0, float(congestion_index)),
                stuck_student_count=max(0, int(stuck_student_count)),
                reroute_count=max(0, int(reroute_count)),
                avg_queue_length=avg_queue_length,
                tray_return_queue_length=max(0, int(tray_return_queue_length)),
            )
        )

    def feed_runtime_sample(
        self,
        game_time: float,
        avg_move_speed: float | None,
        congestion_index: float,
        stuck_student_count: int,
        reroute_count: int,
        avg_queue_length: float | None,
        tray_return_queue_length: int,
    ) -> None:
        self.record_runtime_sample(
            game_time,
            avg_move_speed,
            congestion_index,
            stuck_student_count,
            reroute_count,
            avg_queue_length,
            tray_return_queue_length,
        )

    def student_events(self, student_id: int) -> list[EventRecordP0]:
        return sorted(self.events_by_student.get(student_id, []), key=_event_sort_key)

    def dish_events(self, dish_id: int) -> list[EventRecordP0]:
        return sorted(self.events_by_dish.get(dish_id, []), key=_event_sort_key)

    def order_events(self, order_id: int) -> list[EventRecordP0]:
        return sorted(self.events_by_order.get(order_id, []), key=_event_sort_key)

    def group_events(self, group_id: int) -> list[EventRecordP0]:
        return sorted(self.events_by_group.get(group_id, []), key=_event_sort_key)

    def table_type_events(self, table_type: str) -> list[EventRecordP0]:
        return sorted(self.events_by_table_type.get(table_type, []), key=_event_sort_key)

    def build_stats(self, current_time: float | None = None) -> StatsFrameP0:
        events = sorted(self.events, key=_event_sort_key)
        avg_wait_time = self._average_duration_by_student("queue_started", "food_ready")
        avg_total_time = self._average_duration_by_student("student_spawned", "student_left")
        max_active_students = self._max_active_students(events)
        stall_queue_stats = self._stall_queue_stats(events)
        seat_utilization = self._seat_utilization(current_time)
        order_timing_stats = self._order_timing_stats()
        runtime = self.runtime_samples[-1] if self.runtime_samples else None
        return StatsFrameP0(
            avg_wait_time=avg_wait_time,
            avg_total_time=avg_total_time,
            max_active_students=max_active_students,
            stall_queue_stats=stall_queue_stats,
            seat_utilization=seat_utilization,
            avg_move_speed=runtime.avg_move_speed if runtime else None,
            congestion_index=runtime.congestion_index if runtime else 0.0,
            stuck_student_count=runtime.stuck_student_count if runtime else 0,
            reroute_count=runtime.reroute_count if runtime else 0,
            avg_queue_length=runtime.avg_queue_length if runtime else None,
            tray_return_queue_length=runtime.tray_return_queue_length if runtime else 0,
            dish_sales_stats=self._dish_sales_stats(),
            dish_sold_out_stats=self._dish_sold_out_stats(),
            dish_stock_stats=self._dish_stock_stats(),
            avg_order_wait_time=order_timing_stats["avg_order_wait_time"],
            avg_order_cook_time=order_timing_stats["avg_order_cook_time"],
            avg_order_total_time=order_timing_stats["avg_order_total_time"],
            completed_order_count=order_timing_stats["completed_order_count"],
            cancelled_order_count=order_timing_stats["cancelled_order_count"],
        )

    def _average_duration_by_student(self, start_type: str, end_type: str) -> float | None:
        samples: list[float] = []
        for student_id, student_events in self.events_by_student.items():
            start = _first_event(student_events, start_type)
            if start is None:
                continue
            earlier_end = _first_event(student_events, end_type)
            if earlier_end is not None and earlier_end.game_time < start.game_time:
                self.issues.append(
                    f"negative duration for student {student_id}: {start_type}->{end_type}"
                )
                continue
            end = _first_event(student_events, end_type, min_time=start.game_time)
            if end is None:
                continue

            duration = end.game_time - start.game_time
            if duration < 0:
                self.issues.append(
                    f"negative duration for student {student_id}: {start_type}->{end_type}"
                )
                continue
            samples.append(duration)
        return _average(samples)

    def _max_active_students(self, events: Iterable[EventRecordP0]) -> int:
        active = 0
        maximum = 0
        for event in events:
            if event.event_type == "student_spawned":
                active += 1
                maximum = max(maximum, active)
            elif event.event_type == "student_left":
                active = max(0, active - 1)
        return maximum

    def _stall_queue_stats(self, events: list[EventRecordP0]) -> list[StallQueueStats]:
        sampled_max: dict[int, int] = {}
        for sample in self.queue_samples:
            sampled_max[sample.stall_id] = max(
                sampled_max.get(sample.stall_id, 0),
                sample.queue_length,
            )
        if sampled_max:
            return [
                StallQueueStats(stall_id=stall_id, max_queue_length=max_length)
                for stall_id, max_length in sorted(sampled_max.items())
            ]

        current: dict[int, int] = defaultdict(int)
        maximum: dict[int, int] = {}
        for event in events:
            if event.stall_id is None:
                continue
            if event.event_type == "queue_started":
                current[event.stall_id] += 1
                maximum[event.stall_id] = max(maximum.get(event.stall_id, 0), current[event.stall_id])
            elif event.event_type in ("food_ready", "student_left"):
                current[event.stall_id] = max(0, current[event.stall_id] - 1)

        return [
            StallQueueStats(stall_id=stall_id, max_queue_length=max_length)
            for stall_id, max_length in sorted(maximum.items())
        ]

    def _seat_utilization(self, current_time: float | None) -> float | None:
        if self.total_seats is None or self.total_seats <= 0:
            return None

        denominator_duration = self.duration
        if denominator_duration is None:
            denominator_duration = current_time
        if denominator_duration is None or denominator_duration <= 0:
            return None

        occupied_duration = 0.0
        for seat_key, seat_events in self.events_by_seat.items():
            open_start: EventRecordP0 | None = None
            for event in sorted(seat_events, key=_event_sort_key):
                if event.event_type == "eating_started":
                    open_start = event
                elif event.event_type == "eating_finished" and open_start is not None:
                    duration = event.game_time - open_start.game_time
                    if duration < 0:
                        self.issues.append(f"negative seat duration for seat {seat_key}")
                    else:
                        occupied_duration += duration
                    open_start = None

            if open_start is not None and current_time is not None and current_time >= open_start.game_time:
                occupied_duration += current_time - open_start.game_time

        total_seat_time = self.total_seats * denominator_duration
        if total_seat_time <= 0:
            return None
        return max(0.0, min(1.0, occupied_duration / total_seat_time))

    def _dish_sales_stats(self) -> list[DishSalesStats]:
        grouped: dict[tuple[int, int | None], dict[str, float | int]] = {}
        for event in self.events:
            if event.event_type != "order_completed":
                continue
            dish_id = event.dish_id
            if dish_id is None and event.order_id is not None:
                dish_id = _first_known_int(self.order_events(event.order_id), "dish_id")
            if dish_id is None:
                self.issues.append("order_completed missing dish_id")
                continue

            stall_id = event.stall_id
            if stall_id is None and event.order_id is not None:
                stall_id = _first_known_int(self.order_events(event.order_id), "stall_id")
            quantity = event.quantity
            if quantity is None and event.order_id is not None:
                quantity = _first_known_int(self.order_events(event.order_id), "quantity")
            quantity = max(1, quantity or 1)

            price = event.price
            if price is None and event.order_id is not None:
                price = _first_known_float(self.order_events(event.order_id), "price")
            revenue = quantity * (price or 0.0)

            key = (dish_id, stall_id)
            current = grouped.setdefault(key, {"sales_count": 0, "revenue": 0.0})
            current["sales_count"] = int(current["sales_count"]) + quantity
            current["revenue"] = float(current["revenue"]) + revenue

        return [
            DishSalesStats(
                dish_id=dish_id,
                stall_id=stall_id,
                sales_count=int(values["sales_count"]),
                revenue=float(values["revenue"]),
            )
            for (dish_id, stall_id), values in sorted(
                grouped.items(), key=lambda item: (item[0][0], -1 if item[0][1] is None else item[0][1])
            )
        ]

    def _dish_sold_out_stats(self) -> list[DishSoldOutStats]:
        grouped: dict[tuple[int, int | None], int] = defaultdict(int)
        for event in self.events:
            if event.event_type != "dish_sold_out":
                continue
            if event.dish_id is None:
                self.issues.append("dish_sold_out missing dish_id")
                continue
            grouped[(event.dish_id, event.stall_id)] += 1

        return [
            DishSoldOutStats(dish_id=dish_id, stall_id=stall_id, sold_out_count=count)
            for (dish_id, stall_id), count in sorted(
                grouped.items(), key=lambda item: (item[0][0], -1 if item[0][1] is None else item[0][1])
            )
        ]

    def _dish_stock_stats(self) -> list[DishStockStats]:
        latest: dict[tuple[int, int | None], EventRecordP0] = {}
        for event in sorted(self.events, key=_event_sort_key):
            if event.event_type not in {"dish_stock_changed", "dish_sold_out", "order_completed"}:
                continue
            if event.dish_id is None or event.stock_after is None:
                continue
            latest[(event.dish_id, event.stall_id)] = event

        return [
            DishStockStats(dish_id=dish_id, stall_id=stall_id, stock=max(0, int(event.stock_after or 0)))
            for (dish_id, stall_id), event in sorted(
                latest.items(), key=lambda item: (item[0][0], -1 if item[0][1] is None else item[0][1])
            )
        ]

    def _order_timing_stats(self) -> dict[str, float | int | None]:
        wait_samples: list[float] = []
        cook_samples: list[float] = []
        total_samples: list[float] = []
        completed_order_count = 0
        cancelled_order_count = 0

        for order_id, order_events in self.events_by_order.items():
            events = sorted(order_events, key=_event_sort_key)
            created = _first_event(events, "order_created")
            started = _first_event(events, "order_started")
            completed = _first_event(events, "order_completed")
            cancelled = _first_event(events, "order_cancelled")

            if cancelled is not None:
                cancelled_order_count += 1
            if completed is None:
                continue
            completed_order_count += 1

            if created is not None:
                total_samples.extend(
                    self._duration_sample(order_id, created, completed, "order_created->order_completed")
                )
            if created is not None and started is not None:
                wait_samples.extend(
                    self._duration_sample(order_id, created, started, "order_created->order_started")
                )
            if started is not None:
                cook_samples.extend(
                    self._duration_sample(order_id, started, completed, "order_started->order_completed")
                )

        return {
            "avg_order_wait_time": _average(wait_samples),
            "avg_order_cook_time": _average(cook_samples),
            "avg_order_total_time": _average(total_samples),
            "completed_order_count": completed_order_count,
            "cancelled_order_count": cancelled_order_count,
        }

    def _duration_sample(
        self,
        order_id: int,
        start: EventRecordP0,
        end: EventRecordP0,
        label: str,
    ) -> list[float]:
        duration = end.game_time - start.game_time
        if duration < 0:
            self.issues.append(f"negative order duration for order {order_id}: {label}")
            return []
        return [duration]


def _event_sort_key(event: EventRecordP0) -> tuple[float, int]:
    priority = {
        "student_spawned": 0,
        "queue_started": 1,
        "food_ready": 2,
        "eating_started": 3,
        "eating_finished": 4,
        "student_left": 5,
    }
    return event.game_time, priority.get(event.event_type, 99)


def _first_event(
    events: Iterable[EventRecordP0],
    event_type: str,
    min_time: float | None = None,
) -> EventRecordP0 | None:
    candidates = sorted(events, key=_event_sort_key)
    for event in candidates:
        if event.event_type != event_type:
            continue
        if min_time is not None and event.game_time < min_time:
            continue
        return event
    return None


def _first_known_int(events: Iterable[EventRecordP0], field_name: str) -> int | None:
    for event in sorted(events, key=_event_sort_key):
        value = getattr(event, field_name)
        if value is not None:
            return int(value)
    return None


def _first_known_float(events: Iterable[EventRecordP0], field_name: str) -> float | None:
    for event in sorted(events, key=_event_sort_key):
        value = getattr(event, field_name)
        if value is not None:
            return float(value)
    return None


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
