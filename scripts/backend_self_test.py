from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.entities import SimulationConfig
from models.simulation_engine import SimulationWorker


@dataclass
class Metrics:
    avg_wait_time: float | None
    avg_total_time: float | None
    max_active_students: int
    stall_max_queue: dict[int, int]
    seat_utilization: float | None
    event_counts: dict[str, int]


class FrameDrivenRecorder:
    def __init__(self, table_count: int, seats_per_table: int = 4) -> None:
        self.last_frame: dict[str, Any] | None = None
        self.last_game_time = 0.0
        self.max_active_students = 0
        self.stall_max_queue: dict[int, int] = {}

        self.spawn_time: dict[int, float] = {}
        self.queue_start_time: dict[int, float] = {}
        self.food_ready_time: dict[int, float] = {}
        self.left_time: dict[int, float] = {}
        self.state_by_student: dict[int, str] = {}

        self.wait_samples: list[float] = []
        self.total_samples: list[float] = []

        self.event_counts = {
            "student_spawned": 0,
            "queue_started": 0,
            "food_ready": 0,
            "eating_started": 0,
            "eating_finished": 0,
            "student_left": 0,
        }

        self.total_seat_time = 0.0
        self.occupied_seat_time = 0.0
        self.total_seats = table_count * seats_per_table

    def feed(self, frame: dict[str, Any]) -> None:
        self.last_frame = frame
        game_time = float(frame["game_time"])
        delta = max(0.0, game_time - self.last_game_time)
        self.last_game_time = game_time

        self.max_active_students = max(self.max_active_students, int(frame["active_students"]))
        for stall in frame.get("stalls", []):
            stall_id = int(stall["id"])
            q = int(stall["queue_count"])
            self.stall_max_queue[stall_id] = max(self.stall_max_queue.get(stall_id, 0), q)

        occupied_now = 0
        for table in frame.get("tables", []):
            seat_frames = table.get("seat_frames")
            if seat_frames:
                occupied_now += sum(1 for seat in seat_frames if seat.get("status") == "occupied")
            else:
                occupied_now += int(table.get("occupied", 0))
        self.total_seat_time += self.total_seats * delta
        self.occupied_seat_time += occupied_now * delta

        seen_ids: set[int] = set()
        for student in frame.get("students", []):
            sid = int(student["id"])
            state = str(student["state"])
            seen_ids.add(sid)

            if sid not in self.spawn_time:
                self.spawn_time[sid] = game_time
                self.event_counts["student_spawned"] += 1

            prev = self.state_by_student.get(sid)
            if prev != "queued" and state == "queued":
                self.queue_start_time[sid] = game_time
                self.event_counts["queue_started"] += 1

            if prev == "queued" and state in (
                "searching_seat",
                "moving_to_seat",
                "waiting_seat",
                "eating",
                "moving_to_tray_return",
                "leaving",
            ):
                self.food_ready_time[sid] = game_time
                self.event_counts["food_ready"] += 1
                q0 = self.queue_start_time.get(sid)
                if q0 is not None:
                    self.wait_samples.append(game_time - q0)

            if prev != "eating" and state == "eating":
                self.event_counts["eating_started"] += 1

            if prev == "eating" and state == "moving_to_tray_return":
                self.event_counts["eating_finished"] += 1

            self.state_by_student[sid] = state

        # If a student disappeared from active frame, treat as left.
        current_ids = set(self.state_by_student.keys())
        disappeared = current_ids - seen_ids
        for sid in list(disappeared):
            self.left_time[sid] = game_time
            self.event_counts["student_left"] += 1
            start = self.spawn_time.get(sid)
            if start is not None:
                self.total_samples.append(game_time - start)
            self.state_by_student.pop(sid, None)

    def build_metrics(self) -> Metrics:
        avg_wait = sum(self.wait_samples) / len(self.wait_samples) if self.wait_samples else None
        avg_total = sum(self.total_samples) / len(self.total_samples) if self.total_samples else None
        seat_util = (
            self.occupied_seat_time / self.total_seat_time if self.total_seat_time > 0 else None
        )
        return Metrics(
            avg_wait_time=avg_wait,
            avg_total_time=avg_total,
            max_active_students=self.max_active_students,
            stall_max_queue=dict(sorted(self.stall_max_queue.items())),
            seat_utilization=seat_util,
            event_counts=self.event_counts.copy(),
        )


def run_self_test() -> None:
    config = SimulationConfig(
        sim_minutes=3,
        time_scale=120.0,
        stall_count=6,
        table_count=12,
        seed=12345,
        total_student_count=40,
        max_active_students=40,
    )
    worker = SimulationWorker(config)
    recorder = FrameDrivenRecorder(table_count=config.table_count)

    worker.frameReady.connect(recorder.feed)
    worker.run()
    metrics = recorder.build_metrics()

    print("=== Backend Self Test (Frame-driven) ===")
    print(f"seed: {config.seed}")
    print(f"avg_wait_time: {metrics.avg_wait_time}")
    print(f"avg_total_time: {metrics.avg_total_time}")
    print(f"max_active_students: {metrics.max_active_students}")
    print(f"stall_max_queue: {metrics.stall_max_queue}")
    print(f"seat_utilization: {metrics.seat_utilization}")
    print(f"event_counts: {metrics.event_counts}")
    print_p1_snapshot(recorder.last_frame)


def print_p1_snapshot(frame: dict[str, Any] | None) -> None:
    if frame is None:
        print("p1_snapshot: no frame captured")
        return

    print("=== P1 Dish / Order Snapshot ===")
    sold_out_stalls = []
    total_orders = 0
    for stall in frame.get("stalls", []):
        dishes = stall.get("dishes", [])
        orders = stall.get("orders", [])
        total_orders += len(orders)
        if stall.get("status") == "sold_out":
            sold_out_stalls.append(stall.get("id"))
        stock_text = ", ".join(
            f"{dish.get('name')}#{dish.get('id')} stock={dish.get('stock')} available={dish.get('available')}"
            for dish in dishes[:2]
        )
        order_counts: dict[str, int] = {}
        for order in orders:
            status = str(order.get("status"))
            order_counts[status] = order_counts.get(status, 0) + 1
        print(
            f"stall {stall.get('id')} status={stall.get('status')} "
            f"queue={stall.get('queue_count')} orders={order_counts} dishes=[{stock_text}]"
        )

    student_choices = [
        {
            "id": student.get("id"),
            "dish_id": student.get("dish_id"),
            "order_id": student.get("order_id"),
            "stall_id": student.get("stall_id"),
            "state": student.get("state"),
        }
        for student in frame.get("students", [])[:8]
    ]
    print(f"total_orders: {total_orders}")
    print(f"sold_out_stalls: {sold_out_stalls}")
    print(f"student_choices_sample: {student_choices}")

if __name__ == "__main__":
    run_self_test()
