from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from heapq import heappop, heappush
from os import cpu_count
from typing import Iterable


Point = tuple[float, float]
Cell = tuple[int, int]
PathRequest = (
    tuple[Point, Point, Iterable[Point]]
    | tuple[Point, Point, Iterable[Point], Iterable["NavRect"]]
)
MAX_PATHFINDING_WORKERS = max(1, cpu_count() or 1)


@dataclass(frozen=True)
class NavRect:
    left: float
    top: float
    right: float
    bottom: float
    kind: str = "obstacle"

    def contains(self, x: float, y: float, clearance: float = 0.0) -> bool:
        return (
            self.left - clearance <= x <= self.right + clearance
            and self.top - clearance <= y <= self.bottom + clearance
        )


@dataclass(frozen=True)
class Doorway:
    x: float
    y: float
    width: float
    height: float
    side: str

    def contains(self, x: float, y: float) -> bool:
        if self.side == "left":
            return x <= self.x + self.width * 0.55 and abs(y - self.y) <= self.height * 0.68
        if self.side == "right":
            return x >= self.x - self.width * 0.55 and abs(y - self.y) <= self.height * 0.68
        return abs(x - self.x) <= self.width * 0.5 and abs(y - self.y) <= self.height * 0.5


class GridPathFinder:
    """Stable coarse-grid A* path finder for the canteen map."""

    _DIRECTIONS: tuple[tuple[int, int, float], ...] = (
        (-1, 0, 1.0),
        (1, 0, 1.0),
        (0, -1, 1.0),
        (0, 1, 1.0),
        (-1, -1, 1.42),
        (-1, 1, 1.42),
        (1, -1, 1.42),
        (1, 1, 1.42),
    )

    def __init__(
        self,
        width: float,
        height: float,
        obstacles: Iterable[NavRect],
        doorways: Iterable[Doorway] = (),
        congestion_points: Iterable[Point] = (),
        cell_size: float = 24.0,
        clearance: float = 14.0,
    ) -> None:
        self.width = width
        self.height = height
        self.cell_size = cell_size
        self.clearance = clearance
        self.cols = max(1, int(width // cell_size) + 1)
        self.rows = max(1, int(height // cell_size) + 1)
        self.obstacles = tuple(obstacles)
        self.doorways = tuple(doorways)
        self._cell_points = self._build_cell_points()
        self._passable_grid = self._build_passable_grid()
        self._neighbors_cache = self._build_neighbors_cache()
        self.congestion_points: tuple[Point, ...] = ()
        self.congestion_costs: dict[Cell, float] = {}
        self.set_congestion_points(congestion_points)

    def set_congestion_points(self, congestion_points: Iterable[Point] = ()) -> None:
        self.congestion_points = tuple(congestion_points)
        self.congestion_costs = self._build_congestion_costs()

    def find_path(
        self,
        start: Point,
        target: Point,
        congestion_points: Iterable[Point] | None = None,
        dynamic_obstacles: Iterable[NavRect] = (),
    ) -> list[Point]:
        congestion_costs = (
            self.congestion_costs
            if congestion_points is None
            else self._build_congestion_costs(congestion_points)
        )
        dynamic_obstacles = tuple(dynamic_obstacles)
        dynamic_blocked_cells = self._build_dynamic_blocked_cells(dynamic_obstacles)
        dynamic_costs = self._build_dynamic_obstacle_costs(dynamic_obstacles)
        return self._find_path(start, target, congestion_costs, dynamic_costs, dynamic_blocked_cells, dynamic_obstacles)

    def find_paths_parallel(
        self,
        requests: Iterable[PathRequest],
        max_workers: int | None = None,
    ) -> list[list[Point]]:
        materialized = [self._materialize_request(request) for request in requests]
        if len(materialized) <= 1:
            return [
                self.find_path(start, target, congestion_points, dynamic_obstacles)
                for start, target, congestion_points, dynamic_obstacles in materialized
            ]

        worker_count = self._resolve_worker_count(len(materialized), max_workers)
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="astar") as executor:
            return list(executor.map(self._find_path_request, materialized))

    def _materialize_request(
        self,
        request: PathRequest,
    ) -> tuple[Point, Point, tuple[Point, ...], tuple[NavRect, ...]]:
        if len(request) == 3:
            start, target, congestion_points = request
            dynamic_obstacles: Iterable[NavRect] = ()
        else:
            start, target, congestion_points, dynamic_obstacles = request
        return start, target, tuple(congestion_points), tuple(dynamic_obstacles)

    def _find_path_request(
        self,
        request: tuple[Point, Point, tuple[Point, ...], tuple[NavRect, ...]],
    ) -> list[Point]:
        start, target, congestion_points, dynamic_obstacles = request
        return self.find_path(start, target, congestion_points, dynamic_obstacles)

    def _resolve_worker_count(self, request_count: int, max_workers: int | None = None) -> int:
        if request_count <= 0:
            return 0
        worker_limit = max_workers if max_workers is not None else MAX_PATHFINDING_WORKERS
        return max(1, min(request_count, worker_limit, MAX_PATHFINDING_WORKERS))

    def _find_path(
        self,
        start: Point,
        target: Point,
        congestion_costs: dict[Cell, float],
        dynamic_costs: dict[Cell, float],
        dynamic_blocked_cells: set[Cell],
        dynamic_obstacles: tuple[NavRect, ...],
    ) -> list[Point]:
        start_cell = self._nearest_passable_cell(self.point_to_cell(start), dynamic_blocked_cells)
        target_cell = self._nearest_passable_cell(self.point_to_cell(target), dynamic_blocked_cells)
        if start_cell is None or target_cell is None:
            return [target]
        if start_cell == target_cell:
            return [target]

        came_from = self._astar(start_cell, target_cell, congestion_costs, dynamic_costs, dynamic_blocked_cells)
        if target_cell not in came_from:
            return [target]

        cells = self._reconstruct_cells(came_from, target_cell)
        points = [self.cell_to_point(cell) for cell in cells[1:]]
        points.append(target)
        return self._smooth_points(start, points, dynamic_obstacles)

    def point_to_cell(self, point: Point) -> Cell:
        x, y = point
        col = int(max(0, min(self.cols - 1, x // self.cell_size)))
        row = int(max(0, min(self.rows - 1, y // self.cell_size)))
        return row, col

    def cell_to_point(self, cell: Cell) -> Point:
        row, col = cell
        return self._cell_points[row][col]

    def is_walkable_point(self, point: Point) -> bool:
        return self._is_passable_point(point[0], point[1])

    def _astar(
        self,
        start: Cell,
        target: Cell,
        congestion_costs: dict[Cell, float],
        dynamic_costs: dict[Cell, float],
        dynamic_blocked_cells: set[Cell],
    ) -> dict[Cell, Cell | None]:
        frontier: list[tuple[float, int, float, Cell]] = []
        heappush(frontier, (0.0, 0, 0.0, start))
        came_from: dict[Cell, Cell | None] = {start: None}
        cost_so_far: dict[Cell, float] = {start: 0.0}
        sequence = 0

        while frontier:
            _, _, current_cost, current = heappop(frontier)
            if current_cost != cost_so_far.get(current):
                continue
            if current == target:
                break

            for neighbor, move_cost in self._neighbors(current):
                if neighbor in dynamic_blocked_cells:
                    continue
                new_cost = cost_so_far[current] + move_cost + self._cell_cost(neighbor, congestion_costs, dynamic_costs)
                if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                    cost_so_far[neighbor] = new_cost
                    sequence += 1
                    priority = new_cost + self._heuristic(neighbor, target)
                    heappush(frontier, (priority, sequence, new_cost, neighbor))
                    came_from[neighbor] = current
        return came_from

    def _neighbors(self, cell: Cell) -> Iterable[tuple[Cell, float]]:
        return self._neighbors_cache.get(cell, ())

    def _is_passable_cell(self, cell: Cell) -> bool:
        row, col = cell
        if row < 0 or row >= self.rows or col < 0 or col >= self.cols:
            return False
        return self._passable_grid[row][col]

    def _build_cell_points(self) -> list[list[Point]]:
        return [
            [
                (
                    min(self.width - 24.0, max(24.0, col * self.cell_size + self.cell_size / 2.0)),
                    min(self.height - 24.0, max(24.0, row * self.cell_size + self.cell_size / 2.0)),
                )
                for col in range(self.cols)
            ]
            for row in range(self.rows)
        ]

    def _build_passable_grid(self) -> list[list[bool]]:
        return [
            [self._is_static_passable_cell((row, col)) for col in range(self.cols)]
            for row in range(self.rows)
        ]

    def _is_static_passable_cell(self, cell: Cell) -> bool:
        row, col = cell
        x, y = self._cell_points[row][col]
        margin = 22.0
        if x < margin or x > self.width - margin or y < margin or y > self.height - margin:
            return False

        for rect in self.obstacles:
            if rect.kind == "wall" and any(doorway.contains(x, y) for doorway in self.doorways):
                continue
            if rect.contains(x, y, self.clearance):
                return False

        return True

    def _build_neighbors_cache(self) -> dict[Cell, tuple[tuple[Cell, float], ...]]:
        neighbors_cache: dict[Cell, tuple[tuple[Cell, float], ...]] = {}
        for row in range(self.rows):
            for col in range(self.cols):
                cell = (row, col)
                if not self._is_passable_cell(cell):
                    continue
                neighbors: list[tuple[Cell, float]] = []
                for d_row, d_col, cost in self._DIRECTIONS:
                    neighbor = (row + d_row, col + d_col)
                    if not self._is_passable_cell(neighbor):
                        continue
                    if d_row and d_col:
                        if not self._is_passable_cell((row + d_row, col)):
                            continue
                        if not self._is_passable_cell((row, col + d_col)):
                            continue
                    neighbors.append((neighbor, cost))
                neighbors_cache[cell] = tuple(neighbors)
        return neighbors_cache

    def _is_passable_point(self, x: float, y: float) -> bool:
        margin = 22.0
        if x < margin or x > self.width - margin or y < margin or y > self.height - margin:
            return False

        for rect in self.obstacles:
            if rect.kind == "wall" and any(doorway.contains(x, y) for doorway in self.doorways):
                continue
            if rect.contains(x, y, self.clearance):
                return False
        return True

    def _nearest_passable_cell(self, origin: Cell, dynamic_blocked_cells: set[Cell] | None = None) -> Cell | None:
        dynamic_blocked_cells = dynamic_blocked_cells or set()
        if self._is_passable_cell(origin) and origin not in dynamic_blocked_cells:
            return origin

        origin_row, origin_col = origin
        for radius in range(1, 10):
            candidates: list[Cell] = []
            for row in range(origin_row - radius, origin_row + radius + 1):
                for col in range(origin_col - radius, origin_col + radius + 1):
                    if abs(row - origin_row) != radius and abs(col - origin_col) != radius:
                        continue
                    candidates.append((row, col))
            candidates.sort(key=lambda cell: self._heuristic(cell, origin))
            for cell in candidates:
                if self._is_passable_cell(cell) and cell not in dynamic_blocked_cells:
                    return cell
        return None

    def _cell_cost(
        self,
        cell: Cell,
        congestion_costs: dict[Cell, float],
        dynamic_costs: dict[Cell, float],
    ) -> float:
        return congestion_costs.get(cell, 0.0) + dynamic_costs.get(cell, 0.0)

    def _build_congestion_costs(self, congestion_points: Iterable[Point] | None = None) -> dict[Cell, float]:
        costs: dict[Cell, float] = {}
        points = self.congestion_points if congestion_points is None else congestion_points
        for point in points:
            row, col = self.point_to_cell(point)
            for d_row in range(-2, 3):
                for d_col in range(-2, 3):
                    cell = (row + d_row, col + d_col)
                    if not (0 <= cell[0] < self.rows and 0 <= cell[1] < self.cols):
                        continue
                    distance_cells = max(abs(d_row), abs(d_col))
                    if distance_cells == 0:
                        costs[cell] = costs.get(cell, 0.0) + 3.0
                    elif distance_cells == 1:
                        costs[cell] = costs.get(cell, 0.0) + 2.0
                    else:
                        costs[cell] = costs.get(cell, 0.0) + 0.8
        return costs

    def _build_dynamic_obstacle_costs(self, dynamic_obstacles: Iterable[NavRect]) -> dict[Cell, float]:
        costs: dict[Cell, float] = {}
        for rect in dynamic_obstacles:
            if self._is_hard_dynamic_obstacle(rect):
                continue
            core_cells = self._dynamic_obstacle_core_cells(rect)
            for row, col in core_cells:
                for d_row in range(-2, 3):
                    for d_col in range(-2, 3):
                        cell = (row + d_row, col + d_col)
                        if not self._is_passable_cell(cell):
                            continue
                        distance_cells = max(abs(d_row), abs(d_col))
                        if distance_cells == 0:
                            cost = 18.0
                        elif distance_cells == 1:
                            cost = 6.0
                        else:
                            cost = 2.0
                        costs[cell] = costs.get(cell, 0.0) + cost
        return costs

    def _build_dynamic_blocked_cells(self, dynamic_obstacles: Iterable[NavRect]) -> set[Cell]:
        blocked: set[Cell] = set()
        for rect in dynamic_obstacles:
            if not self._is_hard_dynamic_obstacle(rect):
                continue
            for cell in self._dynamic_obstacle_core_cells(rect):
                if self._is_passable_cell(cell):
                    blocked.add(cell)
        return blocked

    def _is_hard_dynamic_obstacle(self, rect: NavRect) -> bool:
        return rect.kind in {"queued_student", "queue_student"}

    def _dynamic_obstacle_core_cells(self, rect: NavRect) -> set[Cell]:
        left_top = self.point_to_cell((rect.left, rect.top))
        right_bottom = self.point_to_cell((rect.right, rect.bottom))
        min_row = min(left_top[0], right_bottom[0])
        max_row = max(left_top[0], right_bottom[0])
        min_col = min(left_top[1], right_bottom[1])
        max_col = max(left_top[1], right_bottom[1])

        core_cells: set[Cell] = set()
        center = ((rect.left + rect.right) / 2.0, (rect.top + rect.bottom) / 2.0)
        core_cells.add(self.point_to_cell(center))
        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                cell = (row, col)
                x, y = self.cell_to_point(cell)
                if rect.contains(x, y):
                    core_cells.add(cell)
        return core_cells

    def _heuristic(self, first: Cell, second: Cell) -> float:
        d_row = abs(first[0] - second[0])
        d_col = abs(first[1] - second[1])
        diagonal = min(d_row, d_col)
        straight = max(d_row, d_col) - diagonal
        return diagonal * 1.42 + straight

    def _reconstruct_cells(self, came_from: dict[Cell, Cell | None], target: Cell) -> list[Cell]:
        current: Cell | None = target
        cells: list[Cell] = []
        while current is not None:
            cells.append(current)
            current = came_from[current]
        cells.reverse()
        return cells

    def _smooth_points(
        self,
        start: Point,
        points: list[Point],
        dynamic_obstacles: tuple[NavRect, ...] = (),
    ) -> list[Point]:
        if len(points) <= 2:
            return points

        smoothed: list[Point] = []
        anchor = start
        index = 0
        while index < len(points):
            next_index = len(points) - 1
            while next_index > index and not self._has_line_of_sight(anchor, points[next_index], dynamic_obstacles):
                next_index -= 1
            smoothed.append(points[next_index])
            anchor = points[next_index]
            index = next_index + 1
        return smoothed

    def _has_line_of_sight(
        self,
        start: Point,
        end: Point,
        dynamic_obstacles: tuple[NavRect, ...] = (),
    ) -> bool:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = (dx * dx + dy * dy) ** 0.5
        steps = max(1, int(length / max(4.0, self.cell_size / 3.0)))
        for index in range(1, steps + 1):
            ratio = index / steps
            x = start[0] + dx * ratio
            y = start[1] + dy * ratio
            if not self._is_passable_point(x, y):
                return False
            if any(rect.contains(x, y) for rect in dynamic_obstacles):
                return False
        return True
