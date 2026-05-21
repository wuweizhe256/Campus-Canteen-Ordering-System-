from __future__ import annotations

import unittest

from models.entities import Order, OrderStatus, SimulationConfig
from models.simulation_engine import SimulationWorker


class P1FrameContractTest(unittest.TestCase):
    def test_p1_frame_fields_follow_interface_contract(self) -> None:
        worker = SimulationWorker(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240522,
                total_student_count=1,
                max_active_students=1,
            )
        )
        worker._initialize()
        worker._spawn_group(1)

        stall = worker.stalls[0]
        order = Order(
            id=999,
            student_id=1,
            stall_id=stall.id,
            dish_id=stall.dishes[0].id,
            created_at=1.0,
            started_at=None,
            finished_at=None,
            status=OrderStatus.QUEUED,
        )
        stall.orders.append(order)

        frame = worker._build_frame()

        student = frame["students"][0]
        for field in ("preferences", "dish_id", "order_id"):
            self.assertIn(field, student)
        self.assertIsInstance(student["preferences"], dict)

        stall_frame = frame["stalls"][0]
        for field in ("status", "is_congested", "dishes", "orders"):
            self.assertIn(field, stall_frame)
        self.assertIsInstance(stall_frame["dishes"], list)
        self.assertIsInstance(stall_frame["orders"], list)

        dish = stall_frame["dishes"][0]
        for field in ("id", "name", "features", "price", "stock", "cook_time", "available"):
            self.assertIn(field, dish)
        self.assertIsInstance(dish["features"], dict)
        self.assertGreaterEqual(dish["stock"], 0)

        order_frame = stall_frame["orders"][0]
        for field in (
            "id",
            "student_id",
            "stall_id",
            "dish_id",
            "created_at",
            "started_at",
            "finished_at",
            "status",
        ):
            self.assertIn(field, order_frame)
        self.assertEqual(order_frame["status"], "queued")
        self.assertIsNone(order_frame["started_at"])
        self.assertIsNone(order_frame["finished_at"])


if __name__ == "__main__":
    unittest.main()
