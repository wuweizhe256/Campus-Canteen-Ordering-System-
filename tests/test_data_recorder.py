from __future__ import annotations

import unittest

from models.data_recorder import DataRecorder, EventRecordP0


class DataRecorderTest(unittest.TestCase):
    def test_builds_p0_stats_from_events(self) -> None:
        recorder = DataRecorder(total_seats=4, duration=100.0)
        for event in [
            EventRecordP0("student_spawned", 0.0, student_id=1),
            EventRecordP0("student_spawned", 1.0, student_id=2),
            EventRecordP0("queue_started", 10.0, student_id=1, stall_id=3),
            EventRecordP0("queue_started", 12.0, student_id=2, stall_id=3),
            EventRecordP0("food_ready", 18.0, student_id=1, stall_id=3),
            EventRecordP0("eating_started", 25.0, student_id=1, table_id=0, seat_index=1),
            EventRecordP0("food_ready", 26.0, student_id=2, stall_id=3),
            EventRecordP0("eating_finished", 45.0, student_id=1, table_id=0, seat_index=1),
            EventRecordP0("student_left", 60.0, student_id=1),
            EventRecordP0("student_left", 80.0, student_id=2),
        ]:
            recorder.record_event(event)

        stats = recorder.build_stats().to_dict()

        self.assertEqual(stats["avg_wait_time"], 11.0)
        self.assertEqual(stats["avg_total_time"], 69.5)
        self.assertEqual(stats["max_active_students"], 2)
        self.assertEqual(stats["stall_queue_stats"], [{"stall_id": 3, "max_queue_length": 2}])
        self.assertEqual(stats["seat_utilization"], 0.05)

    def test_skips_missing_pairs_without_crashing(self) -> None:
        recorder = DataRecorder(total_seats=4, duration=100.0)
        recorder.record_event(EventRecordP0("student_spawned", 0.0, student_id=1))
        recorder.record_event(EventRecordP0("queue_started", 5.0, student_id=1, stall_id=1))

        stats = recorder.build_stats().to_dict()

        self.assertIsNone(stats["avg_wait_time"])
        self.assertIsNone(stats["avg_total_time"])
        self.assertEqual(stats["max_active_students"], 1)
        self.assertEqual(stats["seat_utilization"], 0.0)

    def test_queue_samples_override_event_derived_queue_length(self) -> None:
        recorder = DataRecorder()
        recorder.record_event(EventRecordP0("queue_started", 1.0, student_id=1, stall_id=2))
        recorder.record_queue_sample(2.0, stall_id=2, queue_length=4)
        recorder.record_queue_sample(3.0, stall_id=2, queue_length=3)

        stats = recorder.build_stats().to_dict()

        self.assertEqual(stats["stall_queue_stats"], [{"stall_id": 2, "max_queue_length": 4}])

    def test_student_event_lookup_is_sorted(self) -> None:
        recorder = DataRecorder()
        recorder.record_event({"event_type": "student_left", "game_time": 30, "student_id": 1})
        recorder.record_event({"event_type": "student_spawned", "game_time": 10, "student_id": 1})

        events = recorder.student_events(1)

        self.assertEqual([event.event_type for event in events], ["student_spawned", "student_left"])


if __name__ == "__main__":
    unittest.main()
