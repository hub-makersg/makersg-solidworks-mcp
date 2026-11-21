"""Grid (round holes) and hex perforation inside a rectangular region."""

from __future__ import annotations

import math

from shapely.geometry import Polygon, box

from ..spec.models import Pattern
from ..spec.rules import Rect
from .shapes import Circle, Cut, Loop


def _hexagon(cx: float, cy: float, across_flats: float) -> Loop:
    r = across_flats / math.sqrt(3)  # circumradius; pointy-top, flats are vertical
    pts = tuple(
        (
            round(cx + r * math.cos(math.radians(90 + 60 * i)), 6),
            round(cy + r * math.sin(math.radians(90 + 60 * i)), 6),
        )
        for i in range(6)
    )
    return Loop(pts)


def fill(area: Rect, pattern: Pattern) -> list[Cut]:
    """Holes of ``pattern`` that fit entirely inside ``area`` shrunk by the margin."""
    m = pattern.margin
    region: Polygon = box(area.x0 + m, area.y0 + m, area.x1 - m, area.y1 - m)
    if region.is_empty or region.area <= 0:
        return []
    pitch = pattern.size + pattern.web
    if pattern.kind == "grid":
        dx = dy = pitch
        stagger = 0.0
    else:
        dx, dy = pitch, pitch * math.sqrt(3) / 2
        stagger = dx / 2
    x0, y0, x1, y1 = region.bounds
    cx_mid, cy_mid = (x0 + x1) / 2, (y0 + y1) / 2
    nx = int((x1 - x0) / dx) + 2
    ny = int((y1 - y0) / dy) + 2
    cuts: list[Cut] = []
    for j in range(-ny, ny + 1):
        cy = cy_mid + j * dy
        shift = stagger if j % 2 else 0.0
        for i in range(-nx, nx + 1):
            cx = cx_mid + i * dx + shift
            if pattern.kind == "grid":
                c = Circle(round(cx, 6), round(cy, 6), pattern.size / 2)
            else:
                c = _hexagon(cx, cy, pattern.size)
            if region.contains(c.shape()):
                cuts.append(c)
    return cuts
