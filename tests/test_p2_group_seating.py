from __future__ import annotations

import unittest

from models.entities import SeatStatus, SimulationConfig
from models.simulation_engine import SimulationWorker


class P2GroupSeatingTest(unittest.TestCase):
    def test_group_member_prefers_same_table(self) -> None:
        worker = SimulationWorker(
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
        worker._initialize()
        worker._spawn_group(2)

        members = sorted(worker.students.values(), key=lambda student: student.id)
        first, second = members

        first_table = worker.tables[1]
        first_seat = first_table.seats[0]
        first_seat.status = SeatStatus.OCCUPIED
        first_seat.student_id = first.id
        first.table_id = first_table.id
        first.seat_index = 0

        second.x = worker.tables[0].x
        second.y = worker.tables[0].y
        free = [
            (table, seat_index)
            for table in worker.tables
            for seat_index in table.free_seat_indexes()
        ]

        table, seat_index, _, _ = worker._best_seat_candidate(second, free)

        self.assertEqual(table.id, first_table.id)
        self.assertNotEqual(seat_index, first.seat_index)


if __name__ == "__main__":
    unittest.main()
