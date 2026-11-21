"""Check a shop DXF before it is handed over."""

from __future__ import annotations

from pathlib import Path

import ezdxf
from shapely.geometry import LineString

from ..geometry.blank import Blank
from .write import BEND_DOWN, BEND_UP, CUT

ALLOWED = {"LINE", "CIRCLE", "LWPOLYLINE"}
TOL = 1e-3


def validate(path: Path, blank: Blank) -> list[str]:
    """Problems found in ``path``; an empty list means the file may go to the shop."""
    doc = ezdxf.readfile(path)
    problems: list[str] = []
    if doc.header.get("$INSUNITS") != 4:
        problems.append("Đơn vị DXF không phải mm ($INSUNITS ≠ 4).")
    seen: set[tuple] = set()
    bend_segments: list[LineString] = []
    for e in doc.modelspace():
        kind, layer = e.dxftype(), e.dxf.layer
        if kind not in ALLOWED:
            problems.append(f"Entity {kind} không được phép trong file cắt.")
            continue
        if layer not in (CUT, BEND_UP, BEND_DOWN):
            problems.append(f"Entity {kind} nằm trên layer lạ '{layer}'.")
        if kind == "LWPOLYLINE":
            pts = [tuple(round(c, 4) for c in p[:2]) for p in e.get_points()]
            if layer == CUT and not e.closed:
                problems.append(f"Đường cắt hở bắt đầu tại ({pts[0][0]:.2f}, {pts[0][1]:.2f}).")
            sig = ("P", frozenset(pts))
        elif kind == "CIRCLE":
            c = e.dxf.center
            sig = ("C", round(c.x, 4), round(c.y, 4), round(e.dxf.radius, 4))
        else:
            a, b = e.dxf.start, e.dxf.end
            sig = ("L", frozenset({(round(a.x, 4), round(a.y, 4)), (round(b.x, 4), round(b.y, 4))}))
            if layer in (BEND_UP, BEND_DOWN):
                bend_segments.append(LineString([(a.x, a.y), (b.x, b.y)]))
        if sig in seen:
            problems.append(f"Entity {kind} bị trùng trên layer {layer}.")
        seen.add(sig)
    for bend in blank.bends:
        line = LineString([(bend.x1, bend.y1), (bend.x2, bend.y2)])
        zone = line.buffer(TOL)
        covered = sum(s.length for s in bend_segments if zone.contains(s))
        if covered < bend.length - TOL:
            problems.append(
                f"Đường gập tại ({bend.x1:.1f}, {bend.y1:.1f})–({bend.x2:.1f}, {bend.y2:.1f}) "
                f"chỉ phủ {covered:.2f}/{bend.length:.2f} mm."
            )
    return problems
