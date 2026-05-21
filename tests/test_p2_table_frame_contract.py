from __future__ import annotations

import unittest

from models.entities import SimulationConfig
from models.simulation_engine import SimulationWorker


class P2TableFrameContractTest(unittest.TestCase):
    def test_p2_table_types_are_generated_and_exported(self) -> None:
        worker = SimulationWorker(
            SimulationConfig(
                sim_minutes=1,
                table_count=6,
                two_person_table_count=2,
                four_person_table_count=3,
                six_person_table_count=1,
                seed=20240522,
                total_student_count=1,
                max_active_students=1,
            )
        )
        worker._initialize()

        frame = worker._build_frame()
        tables = frame["tables"]

        self.assertEqual(len(tables), 6)
        counts_by_type: dict[str, int] = {}
        seats_by_type: dict[str, int] = {}
        for table in tables:
            table_type = table["table_type"]
            counts_by_type[table_type] = counts_by_type.get(table_type, 0) + 1
            seats_by_type[table_type] = table["seat_count"]
            self.assertEqual(len(table["seats"]), table["seat_count"])
            self.assertEqual(len(table["seat_frames"]), table["seat_count"])

        self.assertEqual(counts_by_type, {"two": 2, "four": 3, "six": 1})
        self.assertEqual(seats_by_type, {"two": 2, "four": 4, "six": 6})


if __name__ == "__main__":
    unittest.main()
