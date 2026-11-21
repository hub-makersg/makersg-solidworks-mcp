"""Bend allowance arithmetic and the bend-line record shared by geometry and the builder.

Convention: every bend line is the centreline of its bend-allowance zone, so the flat
material on each side of the line includes half the bend allowance. SolidWorks sketched
bends are created with "bend centre line" position to match.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BendMath:
    thickness: float
    radius: float
    k: float

    def allowance(self, angle_deg: float) -> float:
        return math.radians(angle_deg) * (self.radius + self.k * self.thickness)

    def setback(self, angle_deg: float) -> float:
        """Outside setback: tangent point to the outside mould line."""
        if angle_deg >= 180:
            return self.radius + self.thickness
        return (self.radius + self.thickness) * math.tan(math.radians(angle_deg) / 2)

    def inset(self, angle_deg: float = 90.0) -> float:
        """Distance from the folded outside dimension back to the bend line in the flat."""
        return self.setback(angle_deg) - self.allowance(angle_deg) / 2


@dataclass(frozen=True)
class BendLine:
    """A straight bend in the flat blank. ``order`` 0 is folded first (outermost bends)."""

    x1: float
    y1: float
    x2: float
    y2: float
    angle: float
    kind: str  # "wall", "lip" or "hem"
    order: int
    up: bool = True  # towards the +Z (inside) surface of the flat sheet

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)
