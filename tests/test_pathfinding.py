from __future__ import annotations

import unittest

from models.entities import SimulationConfig, StudentState
from models.pathfinding import MAX_PATHFINDING_WORKERS, GridPathFinder, NavRect
from models.simulation_engine import (
    STUDENT_COLLISION_HEIGHT,
    STUDENT_COLLISION_PADDING,
    STUDENT_COLLISION_FOOT_OFFSET_Y,
    STUDENT_COLLISION_WIDTH,
    SimulationEngine,
    TABLE_OBSTACLE_SIZES,
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

    def test_static_obstacle_covering_target_does_not_force_blocked_endpoint(self) -> None:
        table_obstacle = NavRect(248.0, 92.0, 304.0, 148.0, "table")
        pathfinder = GridPathFinder(width=320.0, height=240.0, obstacles=[table_obstacle])
        start = (48.0, 120.0)
        target = (280.0, 120.0)

        path = pathfinder.find_path(start, target)

        self.assertTrue(path)
        self.assertNotEqual(path[-1], target)
        self.assertFalse(table_obstacle.contains(path[-1][0], path[-1][1]))
        self.assertFalse(_segment_crosses_rect(start, path[0], table_obstacle))
        for first, second in zip(path, path[1:]):
            self.assertFalse(_segment_crosses_rect(first, second, table_obstacle))

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

    def test_existing_navigation_path_is_reused_for_same_goal(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240623,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))
        student.state = StudentState.MOVING_TO_QUEUE
        goal = (260.0, 180.0)
        updated_goal = (262.0, 181.0)
        student.path = [(220.0, 170.0), goal]
        student.path_goal = goal
        student.path_planned_at = engine.game_time
        calls: list[tuple[tuple[float, float], tuple[float, float], int | None]] = []

        def build_path(start, target, ignored_student_id=None):
            calls.append((start, target, ignored_student_id))
            return [target]

        engine._build_navigation_path = build_path

        engine._set_navigation_path(student, updated_goal)

        self.assertEqual(calls, [])
        self.assertEqual(student.path, [(220.0, 170.0), updated_goal])
        self.assertEqual(student.path_goal, updated_goal)

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

    def test_queued_student_is_treated_as_static_path_blocker(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240619,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        queued, moving = list(engine.students.values())[:2]
        stall = engine.stalls[0]
        queued.state = StudentState.QUEUED
        queued.stall_id = stall.id
        queued.x, queued.y = engine._queue_slot_position(stall, 0)
        stall.queue = [queued.id]
        moving.state = StudentState.MOVING_TO_QUEUE
        moving.stall_id = stall.id
        moving.x, moving.y = 190.0, 150.0
        moving.target_x, moving.target_y = engine._queue_slot_position(stall, 1)

        blocker = engine._path_blocking_static_obstacle(moving)

        self.assertIsNotNone(blocker)
        self.assertEqual(blocker.get("kind"), "queued_student")
        self.assertEqual(blocker.get("student_id"), queued.id)

    def test_moving_queue_target_refresh_replans_when_tail_shift_crosses_queue(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240620,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        queued, moving = list(engine.students.values())[:2]
        stall = engine.stalls[0]
        old_target = engine._queue_slot_position(stall, 0)
        new_target = engine._queue_slot_position(stall, 1)
        queued.state = StudentState.QUEUED
        queued.stall_id = stall.id
        queued.x, queued.y = old_target
        stall.queue = [queued.id]
        moving.state = StudentState.MOVING_TO_QUEUE
        moving.stall_id = stall.id
        moving.x, moving.y = 190.0, 150.0
        moving.path = [old_target]
        moving.target_x, moving.target_y = old_target
        calls: list[tuple[tuple[float, float], tuple[float, float], int | None]] = []

        def build_path(start, target, ignored_student_id=None):
            calls.append((start, target, ignored_student_id))
            return [(220.0, 210.0), target]

        engine._build_navigation_path = build_path

        engine._refresh_moving_queue_target(moving)

        self.assertEqual(calls, [((190.0, 150.0), new_target, moving.id)])
        self.assertEqual(moving.path, [(220.0, 210.0), new_target])
        self.assertEqual((moving.target_x, moving.target_y), (220.0, 210.0))

    def test_moving_queue_target_refresh_delays_small_recent_replan(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240624,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        moving = next(iter(engine.students.values()))
        old_target = (320.0, 156.0)
        new_target = (332.0, 156.0)
        moving.state = StudentState.MOVING_TO_QUEUE
        moving.stall_id = engine.stalls[0].id
        moving.x, moving.y = 120.0, 120.0
        moving.path = [(240.0, 150.0), old_target]
        moving.target_x, moving.target_y = moving.path[0]
        moving.path_goal = old_target
        moving.path_planned_at = engine.game_time
        calls: list[tuple[tuple[float, float], tuple[float, float], int | None]] = []

        def build_path(start, target, ignored_student_id=None):
            calls.append((start, target, ignored_student_id))
            return [target]

        engine._queue_target_position = lambda student: new_target
        engine._path_crosses_static_blocking_obstacle = lambda *args, **kwargs: {"kind": "queued_student"}
        engine._build_navigation_path = build_path

        engine._refresh_moving_queue_target(moving)

        self.assertEqual(calls, [])
        self.assertEqual(moving.path, [(240.0, 150.0), new_target])
        self.assertEqual((moving.target_x, moving.target_y), (240.0, 150.0))
        self.assertEqual(moving.path_goal, new_target)

    def test_near_endpoint_dynamic_block_triggers_detour_check(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240625,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        moving, blocker = list(engine.students.values())[:2]
        moving.state = StudentState.LEAVING
        blocker.state = StudentState.LEAVING
        moving.x, moving.y = 900.0, 690.0
        moving.target_x, moving.target_y = 910.0, 690.0
        moving.path = [(910.0, 690.0)]
        blocker.x, blocker.y = 910.0, 690.0
        detour_calls: list[int] = []

        def static_detour(_student):
            self.fail("dynamic blocking should not run static obstacle detour")

        engine._try_static_obstacle_detour = static_detour
        engine._try_local_avoidance_step = lambda student, step_distance: False

        def start_detour(student, students):
            detour_calls.append(student.id)

        engine._try_start_detour = start_detour

        engine._move_student(moving, 0.8, moving.walk_speed)
        engine._move_student(moving, 0.8, moving.walk_speed)

        self.assertEqual(detour_calls, [moving.id])
        self.assertGreaterEqual(moving.stuck_time, 1.6)

    def test_far_target_student_collision_triggers_detour_check(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240626,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        moving, blocker = list(engine.students.values())[:2]
        moving.state = StudentState.LEAVING
        blocker.state = StudentState.LEAVING
        moving.x, moving.y = 900.0, 690.0
        moving.target_x, moving.target_y = 1040.0, 690.0
        moving.path = [(1040.0, 690.0)]
        blocker.x, blocker.y = 916.0, 690.0
        detour_calls: list[int] = []

        def static_detour(_student):
            self.fail("dynamic blocking should not run static obstacle detour")

        engine._try_static_obstacle_detour = static_detour
        engine._try_local_avoidance_step = lambda student, step_distance: False

        def start_detour(student, students):
            detour_calls.append(student.id)

        engine._try_start_detour = start_detour

        engine._move_student(moving, 0.8, 20.0)
        engine._move_student(moving, 0.8, 20.0)

        self.assertEqual(detour_calls, [moving.id])
        self.assertGreaterEqual(moving.stuck_time, 1.6)

    def test_dynamic_detour_rejects_first_waypoint_crossing_queue(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240621,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        queued, moving = list(engine.students.values())[:2]
        stall = engine.stalls[0]
        queued.state = StudentState.QUEUED
        queued.stall_id = stall.id
        queued.x, queued.y = engine._queue_slot_position(stall, 0)
        stall.queue = [queued.id]
        moving.state = StudentState.MOVING_TO_QUEUE
        moving.stall_id = stall.id
        moving.x, moving.y = 190.0, 150.0
        moving.target_x, moving.target_y = engine._queue_slot_position(stall, 1)
        moving.path = [(moving.target_x, moving.target_y)]
        rejected_candidate = (moving.target_x, moving.target_y)
        reroute_calls = 0

        def find_detour(_student, _students):
            return rejected_candidate

        def reroute(_student):
            nonlocal reroute_calls
            reroute_calls += 1
            moving.path = [(240.0, 220.0), (moving.target_x, moving.target_y)]
            return True

        engine._find_detour_point = find_detour
        engine._reroute_student = reroute

        engine._try_start_detour(moving, [queued, moving])

        self.assertEqual(reroute_calls, 1)
        self.assertNotEqual(moving.path[0], rejected_candidate)

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
        self.assertEqual((student.x, student.y), (120.0, 360.0))

    def test_queued_student_block_uses_static_detour_not_local_avoidance(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240629,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        moving, queued = list(engine.students.values())[:2]
        moving.state = StudentState.MOVING_TO_QUEUE
        queued.state = StudentState.QUEUED
        moving.x, moving.y = 200.0, 156.0
        moving.target_x, moving.target_y = 240.0, 156.0
        moving.path = [(240.0, 156.0)]
        queued.x, queued.y = 220.0, 156.0
        local_avoidance_calls = 0
        static_detour_calls = 0

        def local_avoidance(_student, _step_distance):
            nonlocal local_avoidance_calls
            local_avoidance_calls += 1
            return False

        def static_detour(_student):
            nonlocal static_detour_calls
            static_detour_calls += 1
            moving.path = [(210.0, 190.0), (240.0, 156.0)]
            moving.target_x, moving.target_y = moving.path[0]
            return True

        engine._try_local_avoidance_step = local_avoidance
        engine._try_static_obstacle_detour = static_detour

        arrived = engine._move_student(moving, game_delta=1.0, speed=20.0)

        self.assertFalse(arrived)
        self.assertEqual(local_avoidance_calls, 0)
        self.assertEqual(static_detour_calls, 1)
        self.assertEqual((moving.target_x, moving.target_y), (210.0, 190.0))

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

    def test_bottom_walkway_oncoming_student_can_yield_backward(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240627,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        blocker, yielding = list(engine.students.values())[:2]
        walkway_y = engine.bottom_walkway_y - STUDENT_COLLISION_FOOT_OFFSET_Y
        blocker.state = StudentState.LEAVING
        yielding.state = StudentState.LEAVING
        blocker.x, blocker.y = 876.0, walkway_y
        blocker.target_x, blocker.target_y = 1040.0, walkway_y
        yielding.x, yielding.y = 900.0, walkway_y
        yielding.target_x, yielding.target_y = 760.0, walkway_y

        moved = engine._try_oncoming_yield_step(yielding, -1.0, 0.0, 10.0)

        self.assertTrue(moved)
        self.assertGreater(yielding.x, 900.0)
        self.assertFalse(_student_boxes_overlap(engine, yielding, blocker))

    def test_oncoming_yield_runs_outside_bottom_walkway(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240628,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        blocker, yielding = list(engine.students.values())[:2]
        middle_y = 520.0
        blocker.state = StudentState.LEAVING
        yielding.state = StudentState.LEAVING
        blocker.x, blocker.y = 876.0, middle_y
        blocker.target_x, blocker.target_y = 1040.0, middle_y
        yielding.x, yielding.y = 900.0, middle_y
        yielding.target_x, yielding.target_y = 760.0, middle_y

        moved = engine._try_oncoming_yield_step(yielding, -1.0, 0.0, 10.0)

        self.assertTrue(moved)
        self.assertGreater(yielding.x, 900.0)
        self.assertFalse(_student_boxes_overlap(engine, yielding, blocker))

    def test_oncoming_yield_handles_vertical_aisle(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240629,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        blocker, yielding = list(engine.students.values())[:2]
        blocker.state = StudentState.LEAVING
        yielding.state = StudentState.LEAVING
        blocker.x, blocker.y = 720.0, 476.0
        blocker.target_x, blocker.target_y = 720.0, 640.0
        yielding.x, yielding.y = 720.0, 500.0
        yielding.target_x, yielding.target_y = 720.0, 360.0

        moved = engine._try_oncoming_yield_step(yielding, 0.0, -1.0, 10.0)

        self.assertTrue(moved)
        self.assertGreater(yielding.y, 500.0)
        self.assertFalse(_student_boxes_overlap(engine, yielding, blocker))

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

    def test_stuck_recovery_reroutes_after_static_detour_fails(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240612,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))
        student.state = StudentState.MOVING_TO_SEAT
        student.x, student.y = 200.0, 300.0
        student.target_x, student.target_y = 320.0, 300.0
        student.stuck_time = 30.0
        calls: list[str] = []

        def reroute(_student):
            calls.append("reroute")
            student.path = [(280.0, 320.0)]
            return True

        engine._try_static_obstacle_detour = lambda _student: False
        engine._reroute_student = reroute

        recovered = engine._try_recover_stuck_student(student)

        self.assertTrue(recovered)
        self.assertEqual(calls, ["reroute"])
        self.assertEqual((student.x, student.y), (200.0, 300.0))
        self.assertEqual(student.reroute_count, 1)
        self.assertEqual(student.stuck_time, 0.0)

    def test_stuck_recovery_skips_queued_students(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240613,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))
        student.state = StudentState.QUEUED
        student.stuck_time = 30.0

        self.assertFalse(engine._try_recover_stuck_student(student))
        self.assertEqual(student.stuck_time, 30.0)

    def test_stuck_recovery_detours_around_blocking_table(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240614,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))
        table = engine.tables[0]
        start = (table.x - 110.0, table.y - STUDENT_COLLISION_FOOT_OFFSET_Y)
        target = (table.x + 110.0, table.y - STUDENT_COLLISION_FOOT_OFFSET_Y)
        student.state = StudentState.MOVING_TO_SEAT
        student.x, student.y = start
        student.target_x, student.target_y = target
        student.path = [target]
        student.stuck_time = 30.0
        blocking_obstacle = engine._path_blocking_static_obstacle(student)

        recovered = engine._try_recover_stuck_student(student)

        self.assertIsNotNone(blocking_obstacle)
        self.assertTrue(recovered)
        self.assertTrue(student.path)
        self.assertNotEqual(student.path, [target])
        self.assertEqual(student.reroute_count, 1)
        self.assertEqual(student.stuck_time, 0.0)
        self.assertFalse(engine._path_still_crosses_obstacle(start, student.path, blocking_obstacle))

    def test_static_blocked_step_detours_around_table_before_reroute(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240615,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))
        table = engine.tables[0]
        start = (table.x - 110.0, table.y - STUDENT_COLLISION_FOOT_OFFSET_Y)
        target = (table.x + 110.0, table.y - STUDENT_COLLISION_FOOT_OFFSET_Y)
        student.state = StudentState.MOVING_TO_SEAT
        student.x, student.y = start
        student.target_x, student.target_y = target
        student.path = [target]
        engine.game_time = 5.0
        blocking_obstacle = engine._path_blocking_static_obstacle(student)

        arrived = engine._move_student(student, 1.0, 90.0)

        self.assertIsNotNone(blocking_obstacle)
        self.assertFalse(arrived)
        self.assertTrue(student.path)
        self.assertNotEqual(student.path, [target])
        self.assertEqual(student.reroute_count, 1)
        self.assertGreater(student.detour_until, engine.game_time)
        self.assertFalse(engine._path_still_crosses_obstacle(start, student.path, blocking_obstacle))

    def test_lower_left_table_corner_stuck_moves_down_before_reroute(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240631,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))
        table = engine.tables[0]
        obstacle_width, obstacle_height = TABLE_OBSTACLE_SIZES[table.seat_count]
        obstacle_left = table.x - obstacle_width / 2.0
        obstacle_bottom = table.y + obstacle_height / 2.0
        student.state = StudentState.MOVING_TO_SEAT
        student.x = obstacle_left + 4.0
        student.y = obstacle_bottom - STUDENT_COLLISION_FOOT_OFFSET_Y - 4.0
        student.target_x, student.target_y = table.x + 140.0, student.y
        student.path = [(student.target_x, student.target_y)]
        student.stuck_time = 1.1
        student.detour_until = 10.0
        old_y = student.y
        reroute_calls = 0

        def reroute(_student):
            nonlocal reroute_calls
            reroute_calls += 1
            student.path = [(student.x + 40.0, student.y)]
            return True

        engine._reroute_student = reroute

        arrived = engine._move_student(student, 0.2, 20.0)

        self.assertFalse(arrived)
        self.assertGreater(student.y, old_y)
        self.assertEqual(reroute_calls, 1)
        self.assertEqual(student.stuck_time, 0.0)
        self.assertEqual(student.local_avoidance_time, 0.0)

    def test_repeated_table_corner_reroute_offsets_before_replanning(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240632,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))
        table = engine.tables[0]
        obstacle_width, obstacle_height = TABLE_OBSTACLE_SIZES[table.seat_count]
        obstacle_left = table.x - obstacle_width / 2.0
        obstacle_bottom = table.y + obstacle_height / 2.0
        student.state = StudentState.MOVING_TO_SEAT
        student.table_id = table.id
        student.seat_index = 0
        student.x = obstacle_left + 4.0
        student.y = obstacle_bottom - STUDENT_COLLISION_FOOT_OFFSET_Y - 4.0
        student.target_x, student.target_y = table.x + 140.0, student.y
        student.path = [(student.target_x, student.target_y)]
        student.table_corner_reroute_window_started_at = engine.game_time
        student.table_corner_reroute_count = 1
        old_y = student.y
        path_starts: list[tuple[float, float]] = []

        def build_table_path(start_x, start_y, _table, _seat_index, _seat_x, _seat_y):
            path_starts.append((start_x, start_y))
            return [(start_x + 40.0, start_y)]

        engine._build_table_path = build_table_path

        rerouted = engine._reroute_student(student)

        self.assertTrue(rerouted)
        self.assertGreater(student.y, old_y)
        self.assertEqual(path_starts, [(student.x, student.y)])
        self.assertEqual(student.table_corner_reroute_count, 0)
        self.assertIsNone(student.table_corner_reroute_window_started_at)

    def test_table_overlap_timeout_relocates_student_to_empty_space(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240616,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))
        blocked_table = engine.tables[0]
        target_table = engine.tables[1]
        student.state = StudentState.MOVING_TO_SEAT
        student.table_id = target_table.id
        student.seat_index = 0
        student.x = blocked_table.x
        student.y = blocked_table.y - STUDENT_COLLISION_FOOT_OFFSET_Y
        student.target_x, student.target_y = engine._seat_access_position(target_table, 0)
        student.path = [(student.target_x, student.target_y)]
        student.table_overlap_time = 60.0
        student.stuck_time = 60.0

        relocated = engine._try_relocate_from_table_obstacle(student)

        self.assertTrue(relocated)
        self.assertIsNone(engine._student_table_overlap_obstacle(student))
        self.assertTrue(engine._is_static_walkable_point(student.x, student.y))
        self.assertTrue(student.path)
        self.assertEqual(student.table_overlap_time, 0.0)
        self.assertEqual(student.stuck_time, 0.0)
        self.assertGreaterEqual(student.reroute_count, 1)

    def test_table_overlap_relocates_quickly_during_movement(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=2,
                seed=20240630,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))
        blocked_table = engine.tables[0]
        target_table = engine.tables[1]
        student.state = StudentState.MOVING_TO_SEAT
        student.table_id = target_table.id
        student.seat_index = 0
        student.x = blocked_table.x
        student.y = blocked_table.y - STUDENT_COLLISION_FOOT_OFFSET_Y
        student.target_x, student.target_y = engine._seat_access_position(target_table, 0)
        student.path = [(student.target_x, student.target_y)]
        student.table_overlap_time = 1.4

        arrived = engine._move_student(student, game_delta=0.2, speed=20.0)

        self.assertFalse(arrived)
        self.assertIsNone(engine._student_table_overlap_obstacle(student))
        self.assertTrue(engine._is_static_walkable_point(student.x, student.y))
        self.assertEqual(student.table_overlap_time, 0.0)
        self.assertEqual(student.stuck_time, 0.0)
        self.assertGreaterEqual(student.reroute_count, 1)

    def test_table_obstacle_sizes_match_table_visual_footprint(self) -> None:
        self.assertEqual(TABLE_OBSTACLE_SIZES[2], (74.0, 56.0))
        self.assertEqual(TABLE_OBSTACLE_SIZES[4], (88.0, 74.0))
        self.assertEqual(TABLE_OBSTACLE_SIZES[6], (104.0, 88.0))

    def test_bottom_row_tables_keep_clearance_and_use_upper_access(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=24,
                seed=20240617,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        bottom_tables = [table for table in engine.tables if table.y >= 650.0]

        self.assertTrue(bottom_tables)
        for table in bottom_tables:
            obstacle_height = TABLE_OBSTACLE_SIZES[table.seat_count][1]
            self.assertLessEqual(table.y + obstacle_height / 2.0, engine.height - 60.0)
            lower_seats = [
                index
                for index in range(table.seat_count)
                if engine._seat_position(table, index)[1] > table.y
            ]
            for seat_index in lower_seats:
                access = engine._seat_access_position(table, seat_index)
                self.assertLessEqual(access[1], table.y)
                self.assertTrue(engine._is_static_walkable_point(access[0], access[1]))

    def test_bottom_row_table_path_avoids_target_table_obstacle(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                stall_count=2,
                table_count=24,
                seed=20240618,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        target_table = max(engine.tables, key=lambda table: table.y)
        lower_seat_index = max(
            range(target_table.seat_count),
            key=lambda index: engine._seat_position(target_table, index)[1],
        )
        start = (target_table.x, target_table.y - 180.0)
        seat_x, seat_y = engine._seat_position(target_table, lower_seat_index)
        path = engine._build_table_path(start[0], start[1], target_table, lower_seat_index, seat_x, seat_y)
        target_obstacle = next(
            obstacle
            for obstacle in engine._obstacle_frames()
            if obstacle.get("kind") == "table"
            and obstacle["left"] < target_table.x < obstacle["right"]
            and obstacle["top"] < target_table.y < obstacle["bottom"]
        )

        self.assertTrue(path)
        self.assertFalse(engine._path_still_crosses_obstacle(start, path, target_obstacle))

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
        self.assertLessEqual(max_stuck_students, 25)


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
