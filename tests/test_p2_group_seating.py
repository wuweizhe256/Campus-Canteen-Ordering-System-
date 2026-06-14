from __future__ import annotations

import unittest

from models.entities import SeatStatus, SimulationConfig, StudentState
from models.simulation_engine import SimulationEngine
from utils.helpers import distance


class P2GroupSeatingTest(unittest.TestCase):
    def test_companion_ratio_controls_group_generation_without_split_fields(self) -> None:
        solo_engine = SimulationEngine(SimulationConfig(companion_ratio=0.0, seed=20240619))
        group_engine = SimulationEngine(SimulationConfig(companion_ratio=1.0, seed=20240619))

        self.assertTrue(all(solo_engine._choose_group_size() == 1 for _ in range(20)))
        self.assertTrue(all(group_engine._choose_group_size() > 1 for _ in range(20)))

    def test_due_spawn_keeps_companion_group_intact_when_one_student_is_due(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                table_count=3,
                seed=20240620,
                total_student_count=4,
                max_active_students=4,
                companion_ratio=1.0,
            )
        )
        engine.initialize()
        engine._target_spawned_students = lambda: 1
        engine._choose_group_size = lambda: 4

        engine._spawn_due_students()

        self.assertEqual(engine.spawned_students, 4)
        group_ids = {student.group_id for student in engine.students.values()}
        self.assertEqual(len(group_ids), 1)
        self.assertNotIn(None, group_ids)
        self.assertTrue(all(student.group_size == 4 for student in engine.students.values()))

    def test_group_member_prefers_same_table(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                table_count=3,
                two_person_table_count=0,
                four_person_table_count=3,
                six_person_table_count=0,
                seed=20240522,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)

        members = sorted(engine.students.values(), key=lambda student: student.id)
        first, second = members

        first_table = engine.tables[1]
        first_seat = first_table.seats[0]
        first_seat.status = SeatStatus.OCCUPIED
        first_seat.student_id = first.id
        first.table_id = first_table.id
        first.seat_index = 0

        second.x = engine.tables[0].x
        second.y = engine.tables[0].y
        free = [
            (table, seat_index)
            for table in engine.tables
            for seat_index in table.free_seat_indexes()
        ]

        table, seat_index, _, _ = engine._best_seat_candidate(second, free)

        self.assertEqual(table.id, first_table.id)
        self.assertNotEqual(seat_index, first.seat_index)

    def test_seat_paths_end_at_walkable_access_points(self) -> None:
        engine = SimulationEngine(SimulationConfig(seed=20240522))
        engine.initialize()

        for table in engine.tables:
            for seat_index in range(len(table.seats)):
                seat_x, seat_y = engine._seat_position(table, seat_index)
                path = engine._build_table_path(
                    engine.door[0],
                    engine.door[1],
                    table,
                    seat_index,
                    seat_x,
                    seat_y,
                )

                self.assertTrue(path)
                access_x, access_y = path[-1]
                self.assertTrue(engine._is_static_walkable_point(access_x, access_y))

    def test_student_occupies_seat_from_access_point(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=1,
                table_count=1,
                two_person_table_count=0,
                four_person_table_count=1,
                six_person_table_count=0,
                seed=20240522,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))
        table = engine.tables[0]
        seat_index = 0
        seat = table.seats[seat_index]
        seat.status = SeatStatus.RESERVED
        seat.student_id = student.id
        student.table_id = table.id
        student.seat_index = seat_index
        student.state = StudentState.MOVING_TO_SEAT
        student.eating_duration = 300.0
        student.x, student.y = engine._seat_access_position(table, seat_index)
        student.target_x = student.x
        student.target_y = student.y
        student.path.clear()

        engine._update_students(0.1)

        seat_x, seat_y = engine._seat_position(table, seat_index)
        self.assertEqual(student.state, StudentState.EATING)
        self.assertEqual(seat.status, SeatStatus.OCCUPIED)
        self.assertEqual((student.x, student.y), (seat_x, seat_y))

    def test_students_can_leave_every_default_seat_after_eating(self) -> None:
        engine = SimulationEngine(SimulationConfig(seed=20240522))
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))

        for table in engine.tables:
            for seat_index, seat in enumerate(table.seats):
                seat_x, seat_y = engine._seat_position(table, seat_index)
                seat.status = SeatStatus.OCCUPIED
                seat.student_id = student.id
                student.table_id = table.id
                student.seat_index = seat_index
                student.state = StudentState.EATING
                student.x = seat_x
                student.y = seat_y
                student.target_x = seat_x
                student.target_y = seat_y
                student.path.clear()
                student.eating_duration = 1.0
                student.eating_done_at = engine.game_time
                student.stuck_time = 0.0
                student.local_avoidance_time = 0.0

                engine._update_students(0.1)

                self.assertEqual(student.state, StudentState.MOVING_TO_TRAY_RETURN)
                self.assertTrue(engine._is_static_walkable_point(student.x, student.y))
                self.assertTrue(student.path)
                self.assertNotEqual((student.x, student.y), (seat_x, seat_y))
                self.assertEqual(seat.status, SeatStatus.FREE)
                self.assertIsNone(seat.student_id)

    def test_table_frame_includes_occupancy_progress_and_companions(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=10,
                table_count=1,
                two_person_table_count=0,
                four_person_table_count=1,
                six_person_table_count=0,
                seed=20240522,
                total_student_count=2,
                max_active_students=2,
            )
        )
        engine.initialize()
        engine._spawn_group(2)
        table = engine.tables[0]
        members = sorted(engine.students.values(), key=lambda student: student.id)
        engine.game_time = 120.0

        for seat_index, student in enumerate(members):
            table.seats[seat_index].status = SeatStatus.OCCUPIED
            table.seats[seat_index].student_id = student.id
            student.table_id = table.id
            student.seat_index = seat_index
            student.state = StudentState.EATING
            student.eating_duration = 300.0
            student.eating_done_at = 300.0

        table_frame = engine.build_frame()["tables"][0]

        self.assertEqual(table_frame["occupied_count"], 2)
        self.assertEqual(table_frame["reserved_count"], 0)
        self.assertAlmostEqual(table_frame["seat_frames"][0]["student"]["eating_progress"], 0.4)
        self.assertEqual(table_frame["seat_frames"][0]["student"]["companion_ids"], [members[1].id])
        self.assertEqual(table_frame["companion_groups"][0]["member_ids"], [member.id for member in members])

    def test_student_frame_includes_realtime_navigation_details(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=10,
                table_count=1,
                two_person_table_count=0,
                four_person_table_count=1,
                six_person_table_count=0,
                seed=20240522,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))
        student.state = StudentState.MOVING_TO_QUEUE
        engine._start_queue_path(student)
        engine.game_time = student.spawn_time + 42.0

        student_frame = engine.build_frame()["students"][0]

        self.assertEqual(student_frame["path_status"], "active")
        self.assertIsNotNone(student_frame["path_id"])
        self.assertGreater(student_frame["path_waypoint_count"], 0)
        self.assertIsNotNone(student_frame["path_remaining_distance"])
        self.assertEqual(student_frame["queue_position"], 1)
        self.assertIsNotNone(student_frame["dish_name"])
        self.assertEqual(student_frame["time_in_system"], 42.0)

    def test_lightweight_student_frame_keeps_details_out_of_high_frequency_payload(self) -> None:
        engine = SimulationEngine(
            SimulationConfig(
                sim_minutes=10,
                table_count=1,
                two_person_table_count=0,
                four_person_table_count=1,
                six_person_table_count=0,
                seed=20240522,
                total_student_count=1,
                max_active_students=1,
            )
        )
        engine.initialize()
        engine._spawn_group(1)
        student = next(iter(engine.students.values()))
        student.state = StudentState.MOVING_TO_QUEUE
        engine._start_queue_path(student)

        frame = engine.build_frame(lightweight_students=True, include_student_details=True)

        student_frame = frame["students"][0]
        self.assertEqual(student_frame["id"], student.id)
        self.assertEqual(student_frame["state"], "moving_to_queue")
        self.assertIn("facing_x", student_frame)
        self.assertNotIn("path", student_frame)
        self.assertNotIn("preferences", student_frame)
        self.assertNotIn("path_remaining_distance", student_frame)

        detail_frame = frame["student_details"][0]
        self.assertEqual(detail_frame["id"], student.id)
        self.assertIn("path", detail_frame)
        self.assertIn("preferences", detail_frame)
        self.assertIn("path_remaining_distance", detail_frame)

    def test_long_queue_slots_stay_walkable(self) -> None:
        engine = SimulationEngine(SimulationConfig(stall_count=10, table_count=24, seed=20240522))
        engine.initialize()

        for stall in engine.stalls:
            for index in range(30):
                x, y = engine._queue_slot_position(stall, index)
                self.assertTrue(
                    engine._is_static_walkable_point(x, y),
                    f"stall={stall.id} index={index} target=({x:.1f}, {y:.1f})",
                )

    def test_queue_path_segments_do_not_cut_through_tables(self) -> None:
        engine = SimulationEngine(SimulationConfig(stall_count=8, table_count=16, seed=20240522))
        engine.initialize()

        start = (815.7, 351.3)
        target = engine._queue_slot_position(engine.stalls[5], 0)
        path = engine._build_navigation_path(start, target)

        self.assertTrue(path)
        current = start
        for point in path:
            self.assertTrue(self._segment_is_static_walkable(engine, current, point))
            current = point

    @staticmethod
    def _segment_is_static_walkable(
        engine: SimulationEngine,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> bool:
        length = distance(start[0], start[1], end[0], end[1])
        steps = max(1, int(length / 6.0))
        for index in range(1, steps + 1):
            ratio = index / steps
            x = start[0] + (end[0] - start[0]) * ratio
            y = start[1] + (end[1] - start[1]) * ratio
            if not engine._is_static_walkable_point(x, y):
                return False
        return True


if __name__ == "__main__":
    unittest.main()
