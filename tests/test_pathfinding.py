from __future__ import annotations

import unittest

from models.entities import SimulationConfig, StudentState
from models.pathfinding import MAX_PATHFINDING_WORKERS, GridPathFinder, NavRect
from models.simulation_engine import (
    STUDENT_COLLISION_HEIGHT,
    STUDENT_COLLISION_PADDING,
    STUDENT_COLLISION_WIDTH,
    SimulationEngine,
)


class PathFindingThreadingTest(unittest.TestCase):
    def test_parallel_worker_count_is_capped_at_available_threads(self) -> None:
        pathfinder = GridPathFinder(width=320.0, height=240.0, obstacles=[])
        large_request_count = MAX_PATHFINDING_WORKERS + 8

        self.assertEqual(
            pathfinder._resolve_worker_count(large_request_count, max_workers=MAX_PATHFINDING_WORKERS + 99),
            MAX_PATHFINDING_WORKERS,
        )
        self.assertEqual(pathfinder._resolve_worker_count(8, max_workers=MAX_PATHFINDING_WORKERS + 99), min(8, MAX_PATHFINDING_WORKERS))
        self.assertEqual(pathfinder._resolve_worker_count(large_request_count, max_workers=4), min(4, MAX_PATHFINDING_WORKERS))

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

    def test_dynamic_student_obstacle_steers_path_and_smoothing(self) -> None:
        pathfinder = GridPathFinder(width=320.0, height=240.0, obstacles=[])
        dynamic_obstacle = NavRect(130.0, 70.0, 190.0, 170.0, "student")
        start = (48.0, 120.0)
        target = (288.0, 120.0)

        path = pathfinder.find_path(start, target, dynamic_obstacles=[dynamic_obstacle])

        self.assertGreaterEqual(len(path), 2)
        self.assertFalse(_segment_crosses_rect(start, path[0], dynamic_obstacle))
        for first, second in zip(path, path[1:]):
            self.assertFalse(_segment_crosses_rect(first, second, dynamic_obstacle))

    def test_queued_student_obstacles_are_hard_blockers(self) -> None:
        pathfinder = GridPathFinder(width=320.0, height=240.0, obstacles=[])
        queued_obstacle = NavRect(130.0, 70.0, 190.0, 170.0, "queued_student")

        self.assertTrue(pathfinder._build_dynamic_blocked_cells([queued_obstacle]))
        self.assertEqual(pathfinder._build_dynamic_obstacle_costs([queued_obstacle]), {})

    def test_reachable_target_falls_back_when_dynamic_obstacle_covers_goal(self) -> None:
        pathfinder = GridPathFinder(width=320.0, height=240.0, obstacles=[])
        target_obstacle = NavRect(248.0, 92.0, 304.0, 148.0, "queued_student")
        target = (280.0, 120.0)

        path, reachable_target, target_reachable = pathfinder.find_path_to_reachable_target(
            (48.0, 120.0),
            target,
            dynamic_obstacles=[target_obstacle],
        )

        self.assertFalse(target_reachable)
        self.assertTrue(path)
        self.assertEqual(path[-1], reachable_target)
        self.assertFalse(target_obstacle.contains(reachable_target[0], reachable_target[1]))
        self.assertNotEqual(reachable_target, target)

    def test_reachable_target_falls_back_outside_soft_dynamic_goal_obstacle(self) -> None:
        pathfinder = GridPathFinder(width=320.0, height=240.0, obstacles=[])
        target_obstacle = NavRect(248.0, 92.0, 304.0, 148.0, "student")
        target = (280.0, 120.0)

        path, reachable_target, target_reachable = pathfinder.find_path_to_reachable_target(
            (48.0, 120.0),
            target,
            dynamic_obstacles=[target_obstacle],
        )

        self.assertFalse(target_reachable)
        self.assertTrue(path)
        self.assertEqual(path[-1], reachable_target)
        self.assertFalse(target_obstacle.contains(reachable_target[0], reachable_target[1]))
        self.assertNotEqual(reachable_target, target)

    def test_parallel_paths_with_dynamic_obstacles_match_serial_paths(self) -> None:
        pathfinder = GridPathFinder(width=360.0, height=260.0, obstacles=[])
        requests = [
            (
                (48.0, 120.0),
                (310.0, 120.0),
                (),
                (NavRect(130.0, 70.0, 190.0, 170.0, "student"),),
            ),
            (
                (48.0, 200.0),
                (310.0, 60.0),
                ((160.0, 150.0),),
                (NavRect(190.0, 82.0, 232.0, 154.0, "student"),),
            ),
        ]

        serial = [
            pathfinder.find_path(start, target, congestion_points, dynamic_obstacles)
            for start, target, congestion_points, dynamic_obstacles in requests
        ]
        parallel = pathfinder.find_paths_parallel(requests, max_workers=4)

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

        endpoints = [student.path[-1] for student in engine.students.values()]
        self.assertEqual(len(set(endpoints)), len(endpoints))

    def test_moving_students_are_assigned_virtual_queue_tail_slots(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240604,
                total_student_count=3,
                max_active_students=3,
            )
        )
        engine.initialize()
        engine._spawn_group(3)
        students = list(engine.students.values())
        for index, student in enumerate(students):
            student.stall_id = 0
            student.state = StudentState.MOVING_TO_QUEUE
            student.path_started_at = float(index)

        targets = [engine._queue_target_position(student) for student in students]
        expected = [engine._queue_slot_position(engine.stalls[0], index) for index in range(3)]

        self.assertEqual(targets, expected)

    def test_moving_queue_target_is_refreshed_with_tail_shift(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240605,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        queued, moving = list(engine.students.values())[:2]
        queued.stall_id = 0
        queued.state = StudentState.QUEUED
        moving.stall_id = 0
        moving.state = StudentState.MOVING_TO_QUEUE
        old_target = engine._queue_slot_position(engine.stalls[0], 0)
        new_target = engine._queue_slot_position(engine.stalls[0], 1)
        moving.path = [old_target]
        moving.target_x, moving.target_y = old_target
        engine.stalls[0].queue.append(queued.id)

        engine._refresh_moving_queue_target(moving)

        self.assertEqual(moving.path[-1], new_target)
        self.assertEqual((moving.target_x, moving.target_y), new_target)

    def test_collision_boxes_include_non_eating_students_only(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240601,
                total_student_count=3,
                max_active_students=3,
            )
        )
        engine.initialize()
        engine._spawn_group(3)
        students = list(engine.students.values())
        students[0].state = StudentState.MOVING_TO_QUEUE
        students[1].state = StudentState.EATING
        students[2].state = StudentState.DONE

        frame = engine.build_frame()
        student_boxes = [
            box
            for box in frame["collision_boxes"]
            if box.get("kind") == "student"
        ]

        self.assertEqual([box["student_id"] for box in student_boxes], [students[0].id])
        self.assertEqual(student_boxes[0]["width"], STUDENT_COLLISION_WIDTH)
        self.assertEqual(student_boxes[0]["height"], STUDENT_COLLISION_HEIGHT)

    def test_queued_students_are_hard_navigation_obstacles(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240608,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        queued, moving = list(engine.students.values())[:2]
        queued.state = StudentState.QUEUED
        moving.state = StudentState.MOVING_TO_QUEUE

        obstacles = engine._navigation_dynamic_obstacles(ignored_student_id=moving.id)

        self.assertIn("queued_student", {obstacle.kind for obstacle in obstacles})

    def test_seated_students_do_not_need_navigation_work(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240610,
                total_student_count=3,
                max_active_students=3,
            )
        )
        engine.initialize()
        engine._spawn_group(3)
        eating, queued, moving = list(engine.students.values())[:3]
        eating.state = StudentState.EATING
        queued.state = StudentState.QUEUED
        moving.state = StudentState.MOVING_TO_QUEUE

        self.assertFalse(engine._student_needs_navigation_work(eating))
        self.assertFalse(engine._student_needs_navigation_work(queued))
        self.assertTrue(engine._student_needs_navigation_work(moving))

    def test_move_student_avoids_committing_collision_overlap(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240602,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        first, second = list(engine.students.values())[:2]
        first.state = StudentState.MOVING_TO_QUEUE
        second.state = StudentState.MOVING_TO_QUEUE
        first.x, first.y = 200.0, 260.0
        second.x, second.y = 232.0, 260.0
        first.target_x, first.target_y = 240.0, 260.0
        second.target_x, second.target_y = 232.0, 260.0
        first.path.clear()
        second.path.clear()

        engine._move_student(first, game_delta=1.0, speed=20.0)

        self.assertFalse(_student_boxes_overlap(engine, first, second))
        self.assertNotEqual((first.x, first.y), (220.0, 260.0))

    def test_side_clearance_student_does_not_block_forward_motion(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240606,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        first, second = list(engine.students.values())[:2]
        first.state = StudentState.MOVING_TO_QUEUE
        second.state = StudentState.MOVING_TO_QUEUE
        first.x, first.y = 200.0, 300.0
        second.x = 200.0
        second.y = 300.0 + STUDENT_COLLISION_HEIGHT + STUDENT_COLLISION_PADDING / 2.0
        first.target_x, first.target_y = 240.0, 300.0
        first.path.clear()
        second.path.clear()

        engine._move_student(first, game_delta=1.0, speed=20.0)

        self.assertEqual((first.x, first.y), (220.0, 300.0))

    def test_static_obstacle_block_does_not_trigger_local_avoidance_jitter(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240607,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))
        student.state = StudentState.MOVING_TO_QUEUE
        student.stall_id = None
        student.x, student.y = 120.0, 360.0
        student.target_x, student.target_y = 180.0, 360.0
        student.path.clear()
        calls = 0

        def fail_on_local_avoidance(_student, _step_distance):
            nonlocal calls
            calls += 1
            return False

        engine._try_local_avoidance_step = fail_on_local_avoidance

        engine._move_student(student, game_delta=1.0, speed=20.0)

        self.assertEqual(calls, 0)
        self.assertEqual((student.x, student.y), (140.0, 360.0))

    def test_local_avoidance_timeout_triggers_reroute(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240609,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        first, second = list(engine.students.values())[:2]
        first.state = StudentState.MOVING_TO_QUEUE
        second.state = StudentState.MOVING_TO_QUEUE
        first.x, first.y = 200.0, 300.0
        second.x, second.y = 220.0, 300.0
        first.target_x, first.target_y = 240.0, 300.0
        first.local_avoidance_time = 5.5
        first.path = [(240.0, 300.0)]
        reroute_calls = 0

        def reroute(_student):
            nonlocal reroute_calls
            reroute_calls += 1
            first.path = [(260.0, 320.0)]
            return True

        engine._reroute_student = reroute

        arrived = engine._move_student(first, game_delta=1.0, speed=20.0)

        self.assertFalse(arrived)
        self.assertEqual(reroute_calls, 1)
        self.assertEqual(first.reroute_count, 1)
        self.assertEqual(first.local_avoidance_time, 0.0)

    def test_unreachable_endpoint_repair_replaces_path_target(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240611,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))
        student.state = StudentState.MOVING_TO_QUEUE
        student.x, student.y = 200.0, 300.0
        student.target_x, student.target_y = 280.0, 300.0
        student.path = [(280.0, 300.0)]

        def reachable_path(_start, _target, ignored_student_id=None):
            return [(240.0, 332.0)], (240.0, 332.0), False

        engine._build_navigation_path_to_reachable_target = reachable_path

        repaired = engine._repair_unreachable_path_endpoint(student)

        self.assertTrue(repaired)
        self.assertEqual(student.path, [(240.0, 332.0)])
        self.assertEqual((student.target_x, student.target_y), (240.0, 332.0))
        self.assertEqual(student.reroute_count, 1)

    def test_congestion_can_trigger_dynamic_reroute(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=3,
                table_count=3,
                seed=20240603,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        first, second = list(engine.students.values())[:2]
        first.state = StudentState.MOVING_TO_QUEUE
        second.state = StudentState.MOVING_TO_QUEUE
        first.x, first.y = 180.0, 156.0
        second.x, second.y = 198.0, 156.0
        first.target_x, first.target_y = 420.0, 156.0
        first.path = [(420.0, 156.0)]
        first.stuck_time = 1.7
        first.congestion_time = 0.8

        engine._separate_students(0.2)

        self.assertGreaterEqual(first.reroute_count, 1)
        self.assertTrue(first.path)
        self.assertNotEqual(first.path[0], (420.0, 156.0))

    def test_default_load_avoids_persistent_student_box_overlap(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                # Spawning is limited to the first half, so this keeps a 3-minute arrival window.
                sim_minutes=6,
                stall_count=10,
                table_count=24,
                seed=20240522,
                total_student_count=120,
                max_active_students=120,
            )
        )
        engine.initialize()
        overlap_streaks: dict[tuple[int, int], int] = {}
        max_pair_overlap_streak = 0
        max_stuck_students = 0
        for _ in range(140):
            engine.step(1.0)
            overlapping_pairs = _student_overlap_pairs(engine)
            for pair in overlapping_pairs:
                overlap_streaks[pair] = overlap_streaks.get(pair, 0) + 1
                max_pair_overlap_streak = max(max_pair_overlap_streak, overlap_streaks[pair])
            for pair in list(overlap_streaks):
                if pair not in overlapping_pairs:
                    overlap_streaks[pair] = 0
            max_stuck_students = max(
                max_stuck_students,
                sum(
                    1
                    for student in engine.students.values()
                    if student.state not in (StudentState.EATING, StudentState.DONE)
                    and student.stuck_time >= 1.6
                ),
            )

        self.assertLessEqual(max_pair_overlap_streak, 24)
        self.assertLessEqual(max_stuck_students, 20)


def _segment_crosses_rect(
    start: tuple[float, float],
    end: tuple[float, float],
    rect: NavRect,
) -> bool:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    steps = max(1, int(((dx * dx + dy * dy) ** 0.5) / 3.0))
    for index in range(steps + 1):
        ratio = index / steps
        x = start[0] + dx * ratio
        y = start[1] + dy * ratio
        if rect.contains(x, y):
            return True
    return False


def _student_boxes_overlap(engine: SimulationEngine, first, second) -> bool:
    return _rects_overlap(engine._student_collision_rect(first), engine._student_collision_rect(second))


def _student_overlap_pairs(engine: SimulationEngine) -> set[tuple[int, int]]:
    students = [
        student
        for student in engine.students.values()
        if student.state not in (StudentState.EATING, StudentState.DONE)
    ]
    pairs: set[tuple[int, int]] = set()
    for index, first in enumerate(students):
        for second in students[index + 1 :]:
            if _student_boxes_overlap(engine, first, second):
                pairs.add(tuple(sorted((first.id, second.id))))
    return pairs


def _rects_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    return min(first[2], second[2]) > max(first[0], second[0]) and min(first[3], second[3]) > max(first[1], second[1])


if __name__ == "__main__":
    unittest.main()
