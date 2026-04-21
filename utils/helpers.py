from __future__ import annotations

from math import hypot


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def manhattan_2d(ax: float, ay: float, bx: float, by: float) -> float:
    return abs(ax - bx) + abs(ay - by)


def distance(ax: float, ay: float, bx: float, by: float) -> float:
    return hypot(bx - ax, by - ay)


def move_towards(
    x: float,
    y: float,
    target_x: float,
    target_y: float,
    max_distance: float,
) -> tuple[float, float, bool]:
    gap = distance(x, y, target_x, target_y)
    if gap <= max_distance or gap == 0:
        return target_x, target_y, True
    ratio = max_distance / gap
    return x + (target_x - x) * ratio, y + (target_y - y) * ratio, False


def triangle_peak_factor(current: float, duration: float) -> float:
    if duration <= 0:
        return 0.0
    midpoint = duration / 2.0
    return clamp(1.0 - abs(current - midpoint) / midpoint, 0.0, 1.0)
