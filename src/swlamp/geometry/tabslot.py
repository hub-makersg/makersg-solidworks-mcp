"""Straight tab-and-slot joints for flat-pack assembly without welding."""

from __future__ import annotations

from .shapes import Loop

BARE_CLEARANCE = 0.25  # mm total: two laser-cut tolerances


def clearance(coat_um: float) -> float:
    """Total slot oversize: bare fit plus powder coat on both faces of tab and slot."""
    return BARE_CLEARANCE + 4 * coat_um / 1000.0


def slot(
    x: float, y: float, tab_width: float, tab_thickness: float, angle: int, coat_um: float
) -> Loop:
    """Rectangular slot centred on (x, y); ``angle`` 0 puts its long side along x."""
    extra = clearance(coat_um)
    w, h = tab_width + extra, tab_thickness + extra
    if angle == 90:
        w, h = h, w
    pts = (
        (x - w / 2, y - h / 2),
        (x + w / 2, y - h / 2),
        (x + w / 2, y + h / 2),
        (x - w / 2, y + h / 2),
    )
    return Loop(tuple((round(px, 6), round(py, 6)) for px, py in pts))
