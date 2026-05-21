from __future__ import annotations

import unittest

from models.entities import SimulationConfig
from models.simulation_engine import SimulationWorker


class P3ExitFrameTest(unittest.TestCase):
    def test_p3_exits_are_exported_and_nearest_exit_is_selected(self) -> None:
        worker = SimulationWorker(
            SimulationConfig(
                sim_minutes=1,
                seed=20240522,
                total_student_count=1,
                max_active_students=1,
            )
        )
        worker._initialize()
        worker._spawn_group(1)
        student = next(iter(worker.students.values()))

        student.x = 1100.0
        student.y = 180.0
        worker._set_exit_path(student)

        frame = worker._build_frame()

        self.assertEqual(student.exit_id, 2)
        self.assertEqual(len(frame["exits"]), 3)
        for exit_area in frame["exits"]:
            for field in ("id", "x", "y", "width", "height", "is_congested"):
                self.assertIn(field, exit_area)
        self.assertEqual(
            frame["stats"]["exit_flow"],
            [
                {"exit_id": 0, "count": 0},
                {"exit_id": 1, "count": 0},
                {"exit_id": 2, "count": 0},
            ],
        )
        self.assertEqual(frame["students"][0]["exit_id"], 2)


if __name__ == "__main__":
    unittest.main()
