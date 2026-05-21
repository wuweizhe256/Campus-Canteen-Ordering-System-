from __future__ import annotations

import unittest

from models.entities import SimulationConfig
from models.simulation_engine import SimulationWorker


class P3EntranceFrameTest(unittest.TestCase):
    def test_p3_entrances_are_exported_and_count_spawn_flow(self) -> None:
        worker = SimulationWorker(
            SimulationConfig(
                sim_minutes=1,
                entrance_weights=(1.0, 0.0, 0.0),
                seed=20240522,
                total_student_count=4,
                max_active_students=4,
                companion_pair_ratio=0.0,
                companion_multi_ratio=0.0,
            )
        )
        worker._initialize()
        for _ in range(4):
            worker._spawn_group(1)

        frame = worker._build_frame()

        self.assertEqual(len(frame["entrances"]), 3)
        for entrance in frame["entrances"]:
            for field in ("id", "x", "y", "width", "height", "weight"):
                self.assertIn(field, entrance)

        self.assertEqual({student["entrance_id"] for student in frame["students"]}, {0})
        self.assertEqual(
            frame["stats"]["entrance_flow"],
            [
                {"entrance_id": 0, "count": 4},
                {"entrance_id": 1, "count": 0},
                {"entrance_id": 2, "count": 0},
            ],
        )


if __name__ == "__main__":
    unittest.main()
