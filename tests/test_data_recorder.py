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

    def test_records_p1_order_and_dish_events(self) -> None:
        recorder = DataRecorder()
        recorder.record_event(
            {
                "event_type": "order_created",
                "game_time": 10,
                "student_id": 1,
                "stall_id": 2,
                "dish_id": 3,
                "order_id": 4,
                "price": 12.5,
                "quantity": 1,
                "order_status": "queued",
            }
        )
        recorder.record_event(
            {
                "event_type": "dish_sold_out",
                "game_time": 20,
                "stall_id": 2,
                "dish_id": 3,
                "stock_before": 1,
                "stock_after": 0,
            }
        )

        order_events = recorder.order_events(4)
        dish_events = recorder.dish_events(3)

        self.assertEqual([event.event_type for event in order_events], ["order_created"])
        self.assertEqual([event.event_type for event in dish_events], ["order_created", "dish_sold_out"])
        self.assertEqual(order_events[0].price, 12.5)
        self.assertEqual(order_events[0].quantity, 1)

    def test_builds_p1_dish_and_order_stats(self) -> None:
        recorder = DataRecorder()
        for event in [
            {
                "event_type": "order_created",
                "game_time": 10,
                "student_id": 1,
                "stall_id": 2,
                "dish_id": 3,
                "order_id": 100,
                "price": 12.5,
                "quantity": 1,
            },
            {
                "event_type": "order_started",
                "game_time": 14,
                "student_id": 1,
                "stall_id": 2,
                "dish_id": 3,
                "order_id": 100,
            },
            {
                "event_type": "order_completed",
                "game_time": 20,
                "student_id": 1,
                "stall_id": 2,
                "dish_id": 3,
                "order_id": 100,
                "stock_after": 4,
            },
            {
                "event_type": "order_created",
                "game_time": 30,
                "student_id": 2,
                "stall_id": 2,
                "dish_id": 3,
                "order_id": 101,
                "price": 12.5,
                "quantity": 2,
            },
            {
                "event_type": "order_started",
                "game_time": 34,
                "student_id": 2,
                "stall_id": 2,
                "dish_id": 3,
                "order_id": 101,
            },
            {
                "event_type": "order_completed",
                "game_time": 44,
                "student_id": 2,
                "stall_id": 2,
                "dish_id": 3,
                "order_id": 101,
                "stock_after": 2,
            },
            {
                "event_type": "order_created",
                "game_time": 50,
                "student_id": 3,
                "stall_id": 2,
                "dish_id": 4,
                "order_id": 102,
                "price": 8.0,
            },
            {
                "event_type": "order_cancelled",
                "game_time": 55,
                "student_id": 3,
                "stall_id": 2,
                "dish_id": 4,
                "order_id": 102,
            },
            {
                "event_type": "dish_sold_out",
                "game_time": 60,
                "stall_id": 2,
                "dish_id": 3,
                "stock_after": 0,
            },
        ]:
            recorder.record_event(event)

        stats = recorder.build_stats().to_dict()

        self.assertEqual(
            stats["dish_sales_stats"],
            [{"dish_id": 3, "stall_id": 2, "sales_count": 3, "revenue": 37.5}],
        )
        self.assertEqual(
            stats["dish_sold_out_stats"],
            [{"dish_id": 3, "stall_id": 2, "sold_out_count": 1}],
        )
        self.assertEqual(
            stats["dish_stock_stats"],
            [{"dish_id": 3, "stall_id": 2, "stock": 0}],
        )
        self.assertEqual(stats["avg_order_wait_time"], 4.0)
        self.assertEqual(stats["avg_order_cook_time"], 8.0)
        self.assertEqual(stats["avg_order_total_time"], 12.0)
        self.assertEqual(stats["completed_order_count"], 2)
        self.assertEqual(stats["cancelled_order_count"], 1)


if __name__ == "__main__":
    unittest.main()
