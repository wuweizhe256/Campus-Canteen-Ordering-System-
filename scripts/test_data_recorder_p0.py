from __future__ import annotations

from pathlib import Path
import math
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.data_recorder import DataRecorder, EventRecordP0


def main() -> None:
    checks = [
        test_stats_frame_p0_from_events,
        test_missing_pairs_do_not_break_stats,
        test_queue_samples_are_supported,
        test_seat_utilization_null_without_seat_config,
        test_negative_duration_is_reported,
        test_student_event_chain_lookup,
    ]

    failed = 0
    for check in checks:
        try:
            check()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {check.__name__}: {exc}")
        else:
            print(f"PASS {check.__name__}")

    if failed:
        raise SystemExit(f"{failed} P0 data recorder checks failed")
    print("All P0 data recorder checks passed")


def test_stats_frame_p0_from_events() -> None:
    recorder = DataRecorder(total_seats=4, duration=100.0)
    for event in [
        EventRecordP0("student_spawned", 0.0, student_id=1),
        EventRecordP0("student_spawned", 1.0, student_id=2),
        EventRecordP0("queue_started", 10.0, student_id=1, stall_id=3),
        EventRecordP0("queue_started", 12.0, student_id=2, stall_id=3),
        EventRecordP0("food_ready", 18.0, student_id=1, stall_id=3),
        EventRecordP0("food_ready", 26.0, student_id=2, stall_id=3),
        EventRecordP0("eating_started", 25.0, student_id=1, table_id=0, seat_index=1),
        EventRecordP0("eating_finished", 45.0, student_id=1, table_id=0, seat_index=1),
        EventRecordP0("student_left", 60.0, student_id=1),
        EventRecordP0("student_left", 80.0, student_id=2),
    ]:
        recorder.feed_event(event)

    stats = recorder.build_stats().to_dict()
    required_keys = {
        "avg_wait_time",
        "avg_eating_time",
        "avg_total_time",
        "max_active_students",
        "stall_queue_stats",
        "seat_utilization",
        "avg_move_speed",
        "congestion_index",
        "stuck_student_count",
        "reroute_count",
        "avg_queue_length",
        "tray_return_queue_length",
    }
    assert required_keys.issubset(set(stats))
    assert_close(stats["avg_wait_time"], 11.0)
    assert_close(stats["avg_eating_time"], 20.0)
    assert_close(stats["avg_total_time"], 69.5)
    assert stats["max_active_students"] == 2
    assert stats["stall_queue_stats"] == [{"stall_id": 3, "max_queue_length": 2}]
    assert_close(stats["seat_utilization"], 0.05)


def test_missing_pairs_do_not_break_stats() -> None:
    recorder = DataRecorder(total_seats=4, duration=100.0)
    recorder.feed_event({"event_type": "student_spawned", "game_time": 0, "student_id": 1})
    recorder.feed_event({"event_type": "queue_started", "game_time": 5, "student_id": 1, "stall_id": 1})

    stats = recorder.build_stats().to_dict()
    assert stats["avg_wait_time"] is None
    assert stats["avg_total_time"] is None
    assert stats["max_active_students"] == 1
    assert_close(stats["seat_utilization"], 0.0)


def test_queue_samples_are_supported() -> None:
    recorder = DataRecorder()
    recorder.feed_event(EventRecordP0("queue_started", 1.0, student_id=1, stall_id=2))
    recorder.feed_queue_sample(game_time=2.0, stall_id=2, queue_length=4)
    recorder.feed_queue_sample(game_time=3.0, stall_id=2, queue_length=3)

    stats = recorder.build_stats().to_dict()
    assert stats["stall_queue_stats"] == [{"stall_id": 2, "max_queue_length": 4}]


def test_seat_utilization_null_without_seat_config() -> None:
    recorder = DataRecorder()
    recorder.feed_event(EventRecordP0("eating_started", 10.0, student_id=1, table_id=0, seat_index=0))
    recorder.feed_event(EventRecordP0("eating_finished", 20.0, student_id=1, table_id=0, seat_index=0))

    stats = recorder.build_stats().to_dict()
    assert stats["seat_utilization"] is None


def test_negative_duration_is_reported() -> None:
    recorder = DataRecorder()
    recorder.feed_event(EventRecordP0("food_ready", 8.0, student_id=1, stall_id=1))
    recorder.feed_event(EventRecordP0("queue_started", 10.0, student_id=1, stall_id=1))

    stats = recorder.build_stats().to_dict()
    assert stats["avg_wait_time"] is None
    assert any("negative duration" in issue for issue in recorder.issues), recorder.issues


def test_student_event_chain_lookup() -> None:
    recorder = DataRecorder()
    recorder.feed_event({"event_type": "student_left", "game_time": 30, "student_id": 1})
    recorder.feed_event({"event_type": "student_spawned", "game_time": 10, "student_id": 1})

    events = recorder.student_events(1)
    assert [event.event_type for event in events] == ["student_spawned", "student_left"]


def assert_close(actual: Any, expected: float) -> None:
    assert actual is not None, f"expected {expected}, got None"
    assert math.isclose(float(actual), expected, rel_tol=1e-9, abs_tol=1e-9), (
        f"expected {expected}, got {actual}"
    )


if __name__ == "__main__":
    main()
