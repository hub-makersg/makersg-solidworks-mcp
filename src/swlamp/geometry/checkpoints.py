"""Feature-level checkpoints for the folded part.

The overall bounding box only proves the outermost faces. Each checkpoint names one
outside dimension the spec promises (a wall's top, a lip's inner edge, a hem's return
end, a tab's top) and a ray aimed at the face that dimension belongs to. SolidWorks
intersects every ray with the folded body in one call; the first hit along a ray must
land on the predicted coordinate. A wrong K-factor, radius or flange length moves the
face, so the hit misses.

Coordinates are those of the folded part in SolidWorks (mm): base centred on the origin,
outside bottom face at z = −T, walls rising towards +z.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..spec.models import Part

APPROACH = 5.0  # mm of clear space the ray starts from before the face it measures


@dataclass(frozen=True)
class Checkpoint:
    name: str
    axis: int  # 0 = x, 1 = y, 2 = z: the coordinate the hit is judged on
    value: float
    origin: tuple[float, float, float]
    direction: tuple[float, float, float]


def _point(part: Part, side: str, along: float, inward: float, z: float):
    """Part coordinates of a point ``inward`` mm inside a wall's outside face.

    ``along`` is measured along the wall as seen from outside (the spec's face x).
    """
    w, d = part.width / 2, part.depth / 2
    if side == "front":
        return (along, -d + inward, z)
    if side == "back":
        return (-along, d - inward, z)
    if side == "left":
        return (-w + inward, -along, z)
    return (w - inward, along, z)


def _outward(side: str) -> tuple[tuple[float, float, float], int]:
    return {
        "front": ((0.0, -1.0, 0.0), 1),
        "back": ((0.0, 1.0, 0.0), 1),
        "left": ((-1.0, 0.0, 0.0), 0),
        "right": ((1.0, 0.0, 0.0), 0),
    }[side]


def _clear_spot(length: float, blocked: list[tuple[float, float]]) -> float:
    """A position along a wall that no tab covers (tabs stand above the wall top)."""
    for along in (0.0, length / 4, -length / 4, length / 3, -length / 3):
        if all(abs(along - c) > half + 1.0 for c, half in blocked):
            return along
    return length * 0.4


def checkpoints(part: Part, thickness: float, radius: float, tab_len: dict) -> list[Checkpoint]:
    """``tab_len`` maps a wall side to the length of the tabs standing on it."""
    t = thickness
    down, up = (0.0, 0.0, -1.0), (0.0, 0.0, 1.0)
    out: list[Checkpoint] = []
    for side, wall in part.walls.items():
        top = wall.height - t  # outside top in part coordinates
        length = part.width if side in ("front", "back") else part.depth
        tabs = [(at, tb.width / 2) for tb in part.tabs if tb.wall == side for at in tb.at]
        if wall.hem:
            # The fold's top is an arc; its return end is flat, inside the open-hem gap.
            end = top - wall.hem.length
            origin = _point(part, side, 0.0, 1.5 * t + 2 * radius, max(end - APPROACH, end / 2))
            out.append(Checkpoint(f"{side}: đầu hem", 2, end, origin, up))
            continue
        spot = _clear_spot(length, tabs)
        # A lipped wall's top is the bend arc; its flat top is the lip, past the bend.
        across = (radius + t + wall.lip) / 2 if wall.lip else t / 2
        origin = _point(part, side, spot, across, top + APPROACH)
        out.append(Checkpoint(f"{side}: đỉnh vách", 2, top, origin, down))
        if wall.lip:
            direction, axis = _outward(side)
            origin = _point(part, side, 0.0, wall.lip + APPROACH, top - t / 2)
            edge = _point(part, side, 0.0, wall.lip, 0.0)[axis]
            out.append(Checkpoint(f"{side}: mép trong của mép gập", axis, edge, origin, direction))
        if side in tab_len:
            at = tabs[0][0]
            origin = _point(part, side, at, t / 2, top + tab_len[side] + APPROACH)
            out.append(Checkpoint(f"{side}: đỉnh tab", 2, top + tab_len[side], origin, down))
    return out
