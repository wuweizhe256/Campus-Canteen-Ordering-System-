from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.entities import Dish, Entrance, SimulationConfig, Student
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
        self.first_stock_by_key: dict[tuple[int, int], int] = {}
        self.last_stock_by_key: dict[tuple[int, int], int] = {}
        self.dish_name_by_id: dict[int, str] = {}
        self.order_status_history: dict[int, list[str]] = {}
        self.order_dish_by_id: dict[int, int] = {}
        self.student_choice_history: dict[int, list[tuple[int | None, int | None]]] = {}
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
            for dish in stall.get("dishes", []):
                dish_id = int(dish["id"])
                key = (stall_id, dish_id)
                stock = int(dish.get("stock") or 0)
                self.first_stock_by_key.setdefault(key, stock)
                self.last_stock_by_key[key] = stock
                self.dish_name_by_id.setdefault(dish_id, str(dish.get("name") or dish_id))
            for order in stall.get("orders", []):
                order_id = int(order["id"])
                status = str(order.get("status"))
                history = self.order_status_history.setdefault(order_id, [])
                if not history or history[-1] != status:
                    history.append(status)
                if order.get("dish_id") is not None:
                    self.order_dish_by_id[order_id] = int(order["dish_id"])

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
            choice = (_optional_int(student.get("dish_id")), _optional_int(student.get("stall_id")))
            choice_history = self.student_choice_history.setdefault(sid, [])
            if not choice_history or choice_history[-1] != choice:
                choice_history.append(choice)

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
        companion_pair_ratio=0.35,
        companion_multi_ratio=0.2,
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
    print_p1_flow_snapshot(recorder)
    print_p2_group_snapshot(recorder.last_frame)
    print_p2_table_snapshot(recorder.last_frame)
    print_p3_entrance_snapshot(recorder.last_frame)
    print_p3_exit_snapshot(recorder.last_frame)
    print_p3_obstacle_snapshot(recorder.last_frame)
    run_p1_sold_out_self_test()


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
    if frame.get("stats") is not None:
        stats = frame["stats"]
        print(f"dish_sales: {stats.get('dish_sales', [])}")
        print(f"sold_out_counts: {stats.get('sold_out_counts', [])}")
        print(f"avg_order_wait_time: {stats.get('avg_order_wait_time')}")


def print_p1_flow_snapshot(recorder: FrameDrivenRecorder) -> None:
    print("=== P1 Order / Stock Flow ===")
    stock_changes = []
    for key, first_stock in sorted(recorder.first_stock_by_key.items()):
        last_stock = recorder.last_stock_by_key.get(key, first_stock)
        if last_stock != first_stock:
            stall_id, dish_id = key
            stock_changes.append(
                {
                    "stall_id": stall_id,
                    "dish_id": dish_id,
                    "name": recorder.dish_name_by_id.get(dish_id, str(dish_id)),
                    "initial_stock": first_stock,
                    "current_stock": last_stock,
                    "sold": first_stock - last_stock,
                }
            )
    print(f"stock_changes_sample: {stock_changes[:8]}")
    order_flows = [
        {
            "order_id": order_id,
            "dish_id": recorder.order_dish_by_id.get(order_id),
            "statuses": statuses,
        }
        for order_id, statuses in sorted(recorder.order_status_history.items())[:10]
    ]
    print(f"order_status_flows_sample: {order_flows}")
    changed_choices = {
        student_id: choices
        for student_id, choices in sorted(recorder.student_choice_history.items())
        if len(choices) > 1
    }
    print(f"student_rechoice_sample: {dict(list(changed_choices.items())[:8])}")


class LowStockSimulationWorker(SimulationWorker):
    def _build_stall_dishes(self, stall_index: int) -> list[Dish]:
        dishes = super()._build_stall_dishes(stall_index)
        for dish in dishes:
            dish.stock = 1
            dish.cook_time = 2.5
        return dishes

    def _build_student(
        self,
        meat_pref: float,
        veg_pref: float,
        preferences: dict[str, float],
        group_id: int | None,
        group_size: int,
        member_index: int,
        entrance: Entrance,
    ) -> Student:
        student = super()._build_student(
            meat_pref,
            veg_pref,
            preferences,
            group_id,
            group_size,
            member_index,
            entrance,
        )
        student.decision_done_at = self.game_time + self.rng.uniform(1.0, 2.0)
        student.walk_speed = 22.0
        student.table_walk_time = 18.0
        return student


def run_p1_sold_out_self_test() -> None:
    config = SimulationConfig(
        sim_minutes=2,
        time_scale=180.0,
        stall_count=3,
        table_count=8,
        seed=20240522,
        total_student_count=28,
        max_active_students=28,
        companion_pair_ratio=0.0,
        companion_multi_ratio=0.0,
    )
    worker = LowStockSimulationWorker(config)
    recorder = FrameDrivenRecorder(table_count=config.table_count)

    worker.frameReady.connect(recorder.feed)
    worker.run()

    print("=== P1 Low Stock Sold-out Check ===")
    print_p1_snapshot(recorder.last_frame)
    print_p1_flow_snapshot(recorder)


def print_p2_group_snapshot(frame: dict[str, Any] | None) -> None:
    if frame is None:
        print("p2_group_snapshot: no frame captured")
        return

    groups: dict[int, list[dict[str, Any]]] = {}
    solo_count = 0
    for student in frame.get("students", []):
        group_id = student.get("group_id")
        if group_id is None:
            solo_count += 1
            continue
        groups.setdefault(int(group_id), []).append(student)

    print("=== P2 Group Snapshot ===")
    print(f"solo_students_in_frame: {solo_count}")
    print(f"active_group_count: {len(groups)}")
    for group_id, members in sorted(groups.items())[:8]:
        dish_ids = sorted({member.get("dish_id") for member in members})
        stall_ids = sorted({member.get("stall_id") for member in members})
        states = sorted({member.get("state") for member in members})
        declared_sizes = sorted({member.get("group_size") for member in members})
        print(
            f"group {group_id}: members={len(members)} declared_sizes={declared_sizes} "
            f"dishes={dish_ids} stalls={stall_ids} states={states}"
        )


def print_p2_table_snapshot(frame: dict[str, Any] | None) -> None:
    if frame is None:
        print("p2_table_snapshot: no frame captured")
        return

    print("=== P2 Table Type Snapshot ===")
    table_counts: dict[str, int] = {}
    seat_counts: dict[str, int] = {}
    occupied_counts: dict[str, int] = {}
    for table in frame.get("tables", []):
        table_type = str(table.get("table_type") or "four")
        table_counts[table_type] = table_counts.get(table_type, 0) + 1
        seat_counts[table_type] = seat_counts.get(table_type, 0) + int(table.get("seat_count") or 0)
        occupied_counts[table_type] = occupied_counts.get(table_type, 0) + int(table.get("occupied") or 0)

    stats = frame.get("stats") if isinstance(frame.get("stats"), dict) else {}
    print(f"table_counts: {dict(sorted(table_counts.items()))}")
    print(f"seat_counts: {dict(sorted(seat_counts.items()))}")
    print(f"occupied_counts: {dict(sorted(occupied_counts.items()))}")
    print(f"table_type_utilization: {stats.get('table_type_utilization', {})}")
    print(f"group_same_table_rate: {stats.get('group_same_table_rate')}")


def print_p3_entrance_snapshot(frame: dict[str, Any] | None) -> None:
    if frame is None:
        print("p3_entrance_snapshot: no frame captured")
        return

    print("=== P3 Entrance Snapshot ===")
    entrances = [
        {
            "id": entrance.get("id"),
            "x": entrance.get("x"),
            "y": entrance.get("y"),
            "weight": entrance.get("weight"),
        }
        for entrance in frame.get("entrances", [])
    ]
    students_by_entrance: dict[int, int] = {}
    for student in frame.get("students", []):
        entrance_id = student.get("entrance_id")
        if entrance_id is None:
            continue
        entrance_key = int(entrance_id)
        students_by_entrance[entrance_key] = students_by_entrance.get(entrance_key, 0) + 1
    stats = frame.get("stats") if isinstance(frame.get("stats"), dict) else {}
    print(f"entrances: {entrances}")
    print(f"active_students_by_entrance: {dict(sorted(students_by_entrance.items()))}")
    print(f"entrance_flow: {stats.get('entrance_flow', [])}")


def print_p3_exit_snapshot(frame: dict[str, Any] | None) -> None:
    if frame is None:
        print("p3_exit_snapshot: no frame captured")
        return

    print("=== P3 Exit Snapshot ===")
    exits = [
        {
            "id": exit_area.get("id"),
            "x": exit_area.get("x"),
            "y": exit_area.get("y"),
            "is_congested": exit_area.get("is_congested"),
        }
        for exit_area in frame.get("exits", [])
    ]
    leaving_by_exit: dict[int, int] = {}
    for student in frame.get("students", []):
        exit_id = student.get("exit_id")
        if exit_id is None:
            continue
        exit_key = int(exit_id)
        leaving_by_exit[exit_key] = leaving_by_exit.get(exit_key, 0) + 1
    stats = frame.get("stats") if isinstance(frame.get("stats"), dict) else {}
    print(f"exits: {exits}")
    print(f"active_students_by_exit: {dict(sorted(leaving_by_exit.items()))}")
    print(f"exit_flow: {stats.get('exit_flow', [])}")


def print_p3_obstacle_snapshot(frame: dict[str, Any] | None) -> None:
    if frame is None:
        print("p3_obstacle_snapshot: no frame captured")
        return

    print("=== P3 Obstacle / Path Snapshot ===")
    obstacle_counts: dict[str, int] = {}
    for obstacle in frame.get("obstacles", []):
        kind = str(obstacle.get("kind") or "unknown")
        obstacle_counts[kind] = obstacle_counts.get(kind, 0) + 1
    walk_paths = frame.get("walk_paths") or []
    path_debug_lines = frame.get("path_debug_lines") or []
    print(f"obstacle_counts: {dict(sorted(obstacle_counts.items()))}")
    print(f"walk_path_count: {len(walk_paths)}")
    print(f"path_debug_line_count: {len(path_debug_lines)}")
    print(f"obstacle_sample: {frame.get('obstacles', [])[:5]}")


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


if __name__ == "__main__":
    run_self_test()
