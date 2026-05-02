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


@dataclass(frozen=True)
class EventRecordP0:
    event_type: str
    game_time: float
    student_id: int | None = None
    stall_id: int | None = None
    table_id: int | None = None
    seat_index: int | None = None
    from_state: str | None = None
    to_state: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "EventRecordP0":
        return cls(
            event_type=str(value["event_type"]),
            game_time=float(value["game_time"]),
            student_id=_optional_int(value.get("student_id")),
            stall_id=_optional_int(value.get("stall_id")),
            table_id=_optional_int(value.get("table_id")),
            seat_index=_optional_int(value.get("seat_index")),
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
class StatsFrameP0:
    avg_wait_time: float | None
    avg_total_time: float | None
    max_active_students: int
    stall_queue_stats: list[StallQueueStats]
    seat_utilization: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "avg_wait_time": self.avg_wait_time,
            "avg_total_time": self.avg_total_time,
            "max_active_students": self.max_active_students,
            "stall_queue_stats": [item.to_dict() for item in self.stall_queue_stats],
            "seat_utilization": self.seat_utilization,
        }


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
        self.events_by_seat: dict[tuple[int, int], list[EventRecordP0]] = defaultdict(list)
        self.queue_samples: list[QueueLengthSample] = []
        self.issues: list[str] = []

    def record_event(self, event: EventRecordP0 | dict[str, Any]) -> None:
        record = EventRecordP0.from_mapping(event) if isinstance(event, dict) else event
        if record.event_type not in P0_EVENT_TYPES:
            self.issues.append(f"unknown event_type: {record.event_type}")
            return

        self.events.append(record)
        if record.student_id is not None:
            self.events_by_student[record.student_id].append(record)
        if record.stall_id is not None:
            self.events_by_stall[record.stall_id].append(record)
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

    def student_events(self, student_id: int) -> list[EventRecordP0]:
        return sorted(self.events_by_student.get(student_id, []), key=_event_sort_key)

    def build_stats(self, current_time: float | None = None) -> StatsFrameP0:
        events = sorted(self.events, key=_event_sort_key)
        avg_wait_time = self._average_duration_by_student("queue_started", "food_ready")
        avg_total_time = self._average_duration_by_student("student_spawned", "student_left")
        max_active_students = self._max_active_students(events)
        stall_queue_stats = self._stall_queue_stats(events)
        seat_utilization = self._seat_utilization(current_time)
        return StatsFrameP0(
            avg_wait_time=avg_wait_time,
            avg_total_time=avg_total_time,
            max_active_students=max_active_students,
            stall_queue_stats=stall_queue_stats,
            seat_utilization=seat_utilization,
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
