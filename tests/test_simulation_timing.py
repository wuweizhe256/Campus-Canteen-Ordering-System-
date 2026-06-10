from __future__ import annotations

import unittest

from models.entities import SimulationConfig
from models.simulation_engine import (
    STALL_COOK_TIME_MAX_SECONDS,
    STALL_COOK_TIME_MIN_SECONDS,
    SimulationEngine,
)


class SimulationTimingTest(unittest.TestCase):
    def test_stall_cook_time_is_uniform_window_range(self) -> None:
        engine = SimulationEngine(SimulationConfig(stall_count=10, seed=20240522))
        engine.initialize()

        for stall in engine.stalls:
            self.assertGreaterEqual(stall.cook_time, STALL_COOK_TIME_MIN_SECONDS)
            self.assertLessEqual(stall.cook_time, STALL_COOK_TIME_MAX_SECONDS)
            self.assertTrue(stall.dishes)
            for dish in stall.dishes:
                self.assertEqual(dish.cook_time, stall.cook_time)

    def test_order_ready_time_uses_stall_cook_time(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=4,
                table_count=4,
                seed=20240522,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))

        engine._join_stall_queue(student)

        stall = engine.stalls[student.stall_id]
        order = stall.orders[-1]
        self.assertEqual(order.finished_at - order.started_at, stall.cook_time)


if __name__ == "__main__":
    unittest.main()
