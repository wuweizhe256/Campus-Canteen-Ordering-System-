from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from math import hypot
from typing import Iterable


Point = tuple[float, float]
Cell = tuple[int, int]


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
        self.congestion_points = tuple(congestion_points)
        self.congestion_costs = self._build_congestion_costs()
        self._passable_cache: dict[Cell, bool] = {}

    def find_path(self, start: Point, target: Point) -> list[Point]:
        start_cell = self._nearest_passable_cell(self.point_to_cell(start))
        target_cell = self._nearest_passable_cell(self.point_to_cell(target))
        if start_cell is None or target_cell is None:
            return [target]
        if start_cell == target_cell:
            return [target]

        came_from = self._astar(start_cell, target_cell)
        if target_cell not in came_from:
            return [target]

        cells = self._reconstruct_cells(came_from, target_cell)
        points = [self.cell_to_point(cell) for cell in cells[1:]]
        points.append(target)
        return self._smooth_points(start, points)

    def point_to_cell(self, point: Point) -> Cell:
        x, y = point
        col = int(max(0, min(self.cols - 1, x // self.cell_size)))
        row = int(max(0, min(self.rows - 1, y // self.cell_size)))
        return row, col

    def cell_to_point(self, cell: Cell) -> Point:
        row, col = cell
        x = min(self.width - 24.0, max(24.0, col * self.cell_size + self.cell_size / 2.0))
        y = min(self.height - 24.0, max(24.0, row * self.cell_size + self.cell_size / 2.0))
        return x, y

    def is_walkable_point(self, point: Point) -> bool:
        return self._is_passable_point(point[0], point[1])

    def _astar(self, start: Cell, target: Cell) -> dict[Cell, Cell | None]:
        frontier: list[tuple[float, int, Cell]] = []
        heappush(frontier, (0.0, 0, start))
        came_from: dict[Cell, Cell | None] = {start: None}
        cost_so_far: dict[Cell, float] = {start: 0.0}
        sequence = 0

        while frontier:
            _, _, current = heappop(frontier)
            if current == target:
                break

            for neighbor, move_cost in self._neighbors(current):
                new_cost = cost_so_far[current] + move_cost + self._cell_cost(neighbor)
                if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                    cost_so_far[neighbor] = new_cost
                    sequence += 1
                    priority = new_cost + self._heuristic(neighbor, target)
                    heappush(frontier, (priority, sequence, neighbor))
                    came_from[neighbor] = current
        return came_from

    def _neighbors(self, cell: Cell) -> Iterable[tuple[Cell, float]]:
        row, col = cell
        directions = (
            (-1, 0, 1.0),
            (1, 0, 1.0),
            (0, -1, 1.0),
            (0, 1, 1.0),
            (-1, -1, 1.42),
            (-1, 1, 1.42),
            (1, -1, 1.42),
            (1, 1, 1.42),
        )
        for d_row, d_col, cost in directions:
            neighbor = (row + d_row, col + d_col)
            if not self._is_passable_cell(neighbor):
                continue
            if d_row and d_col:
                if not self._is_passable_cell((row + d_row, col)):
                    continue
                if not self._is_passable_cell((row, col + d_col)):
                    continue
            yield neighbor, cost

    def _is_passable_cell(self, cell: Cell) -> bool:
        if cell in self._passable_cache:
            return self._passable_cache[cell]

        row, col = cell
        if row < 0 or row >= self.rows or col < 0 or col >= self.cols:
            self._passable_cache[cell] = False
            return False

        x, y = self.cell_to_point(cell)
        margin = 22.0
        if x < margin or x > self.width - margin or y < margin or y > self.height - margin:
            self._passable_cache[cell] = False
            return False

        for rect in self.obstacles:
            if rect.kind == "wall" and any(doorway.contains(x, y) for doorway in self.doorways):
                continue
            if rect.contains(x, y, self.clearance):
                self._passable_cache[cell] = False
                return False

        self._passable_cache[cell] = True
        return True

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

    def _nearest_passable_cell(self, origin: Cell) -> Cell | None:
        if self._is_passable_cell(origin):
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
                if self._is_passable_cell(cell):
                    return cell
        return None

    def _cell_cost(self, cell: Cell) -> float:
        return self.congestion_costs.get(cell, 0.0)

    def _build_congestion_costs(self) -> dict[Cell, float]:
        costs: dict[Cell, float] = {}
        for point in self.congestion_points:
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

    def _heuristic(self, first: Cell, second: Cell) -> float:
        return hypot(first[0] - second[0], first[1] - second[1])

    def _reconstruct_cells(self, came_from: dict[Cell, Cell | None], target: Cell) -> list[Cell]:
        current: Cell | None = target
        cells: list[Cell] = []
        while current is not None:
            cells.append(current)
            current = came_from[current]
        cells.reverse()
        return cells

    def _smooth_points(self, start: Point, points: list[Point]) -> list[Point]:
        if len(points) <= 2:
            return points

        smoothed: list[Point] = []
        anchor = start
        index = 0
        while index < len(points):
            next_index = len(points) - 1
            while next_index > index and not self._has_line_of_sight(anchor, points[next_index]):
                next_index -= 1
            smoothed.append(points[next_index])
            anchor = points[next_index]
            index = next_index + 1
        return smoothed

    def _has_line_of_sight(self, start: Point, end: Point) -> bool:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        steps = max(1, int(hypot(dx, dy) / max(3.0, self.cell_size * 0.15)))
        for index in range(1, steps + 1):
            ratio = index / steps
            point = (start[0] + dx * ratio, start[1] + dy * ratio)
            if not self.is_walkable_point(point):
                return False
        return True
