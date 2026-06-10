from __future__ import annotations

import unittest

from models.entities import SimulationConfig, StudentState
from models.pathfinding import GridPathFinder, NavRect
from models.simulation_engine import SimulationEngine


class PathFindingThreadingTest(unittest.TestCase):
    def test_parallel_paths_match_serial_paths(self) -> None:
        pathfinder = GridPathFinder(
            width=320.0,
            height=240.0,
            obstacles=[
                NavRect(120.0, 40.0, 150.0, 170.0, "column"),
                NavRect(210.0, 80.0, 240.0, 210.0, "column"),
            ],
        )
        requests = [
            ((48.0, 48.0), (288.0, 192.0), ()),
            ((48.0, 192.0), (288.0, 48.0), ((160.0, 120.0),)),
            ((84.0, 48.0), (268.0, 200.0), ((180.0, 120.0), (200.0, 140.0))),
        ]

        serial = [
            pathfinder.find_path(start, target, congestion_points)
            for start, target, congestion_points in requests
        ]
        parallel = pathfinder.find_paths_parallel(requests, max_workers=3)

        self.assertEqual(parallel, serial)

    def test_due_queue_paths_are_planned_in_batch(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=4,
                table_count=4,
                seed=20240522,
                total_student_count=4,
                max_active_students=4,
            )
        )
        engine.initialize()
        engine._spawn_group(4)
        for student in engine.students.values():
            student.decision_done_at = engine.game_time

        engine._start_due_queue_paths_parallel()

        self.assertTrue(engine.students)
        for student in engine.students.values():
            self.assertEqual(student.state, StudentState.MOVING_TO_QUEUE)
            self.assertTrue(student.path)
            self.assertIsNotNone(student.path_id)


if __name__ == "__main__":
    unittest.main()
