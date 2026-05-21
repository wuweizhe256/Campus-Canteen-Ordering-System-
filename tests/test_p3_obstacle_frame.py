from __future__ import annotations

import unittest

from models.entities import SimulationConfig
from models.simulation_engine import SimulationWorker


class P3ObstacleFrameTest(unittest.TestCase):
    def test_p3_obstacles_and_debug_paths_are_exported(self) -> None:
        worker = SimulationWorker(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=3,
                two_person_table_count=1,
                four_person_table_count=1,
                six_person_table_count=1,
                seed=20240522,
                total_student_count=1,
                max_active_students=1,
            )
        )
        worker._initialize()

        frame = worker._build_frame()

        self.assertIn("obstacles", frame)
        self.assertIn("walk_paths", frame)
        self.assertIn("path_debug_lines", frame)
        self.assertIsInstance(frame["obstacles"], list)
        self.assertIsInstance(frame["walk_paths"], list)
        self.assertIsInstance(frame["path_debug_lines"], list)
        self.assertEqual(frame["path_debug_lines"], frame["walk_paths"])

        kinds = {obstacle["kind"] for obstacle in frame["obstacles"]}
        self.assertTrue({"stall", "table", "wall"}.issubset(kinds))
        for obstacle in frame["obstacles"]:
            for field in ("left", "top", "right", "bottom", "kind"):
                self.assertIn(field, obstacle)
            self.assertLess(obstacle["left"], obstacle["right"])
            self.assertLess(obstacle["top"], obstacle["bottom"])


if __name__ == "__main__":
    unittest.main()
