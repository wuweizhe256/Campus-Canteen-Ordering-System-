from __future__ import annotations

import unittest

from models.entities import SeatStatus, SimulationConfig, StudentState
from models.simulation_engine import SimulationEngine
from utils.helpers import distance


class P2GroupSeatingTest(unittest.TestCase):
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
