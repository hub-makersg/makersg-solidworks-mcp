"""Cut primitives. Circles stay true circles so the DXF and the SolidWorks sketch get arcs."""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Point, Polygon


@dataclass(frozen=True)
class Circle:
    cx: float
    cy: float
    r: float

    def shape(self) -> Polygon:
        return Point(self.cx, self.cy).buffer(self.r, quad_segs=32)


@dataclass(frozen=True)
class Loop:
    """A closed polyline cut (points without the repeated first point)."""

    points: tuple[tuple[float, float], ...]

    def shape(self) -> Polygon:
        return Polygon(self.points)


Cut = Circle | Loop


def loops_of(poly: Polygon) -> list[Loop]:
    """Exterior ring of a polygon as a cut loop; callers reject interiors (islands) first."""
    coords = list(poly.exterior.coords)[:-1]
    return [Loop(tuple((round(x, 6), round(y, 6)) for x, y in coords))]
