"""A tap point to a token and its sentence. Pure: the prototype of the app's `photoText.ts`."""

from __future__ import annotations

import math
from typing import Any

# How far outside a word's polygon a tap may land and still select it, as a fraction of the image
# width. A fingertip is wide and the word is small.
TOLERANCE = 0.03


def _inside(point: tuple[float, float], polygon: list[list[float]]) -> bool:
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-9) + x1:
            inside = not inside
    return inside


def _distance(point: tuple[float, float], polygon: list[list[float]]) -> float:
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    dx = max(min(xs) - point[0], 0, point[0] - max(xs))
    dy = max(min(ys) - point[1], 0, point[1] - max(ys))
    return math.hypot(dx, dy)


def token_at(tokens: list[dict[str, Any]], point: tuple[float, float]) -> int | None:
    best, best_distance = None, TOLERANCE
    for index, token in enumerate(tokens):
        for polygon in token["polygons"]:
            if _inside(point, polygon):
                return index
            distance = _distance(point, polygon)
            if distance < best_distance:
                best, best_distance = index, distance
    return best


def sentence_of(sentences: list[tuple[int, int]], token: dict[str, Any]) -> int | None:
    for index, (start, end) in enumerate(sentences):
        if start <= token["start"] < end:
            return index
    return None
