"""Compare SolidWorks' own flat-pattern export with the shop DXF.

This only proves SolidWorks built the geometry that was sent to it; whether the
dimensions are right is checked separately on the folded part. Bend lines (dashed in
the SolidWorks export) are ignored; every other curve is treated as cut geometry.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf
import shapely
from ezdxf import path as ezpath
from shapely import affinity
from shapely.geometry import LineString, MultiLineString
from shapely.ops import unary_union

from .write import CUT

FLATNESS = 0.005


def _cut_lines(path: Path, only_layer: str | None) -> MultiLineString:
    doc = ezdxf.readfile(path)
    lines = []
    for e in doc.modelspace():
        if only_layer is not None and e.dxf.layer != only_layer:
            continue
        if only_layer is None and e.dxf.get("linetype", "").upper() not in (
            "",
            "CONTINUOUS",
            "BYLAYER",
        ):
            continue  # SolidWorks draws bend lines with a dashed linetype
        try:
            p = ezpath.make_path(e)
        except (TypeError, ValueError):
            continue
        for sub in p.sub_paths():
            pts = [(v.x, v.y) for v in sub.flattening(FLATNESS)]
            if len(pts) >= 2:
                lines.append(LineString(pts))
    return unary_union(lines)


def _deviation(a, b) -> float:
    """Largest distance from any point of ``a`` (sampled every 0.5 mm) to ``b``."""
    pts = shapely.points(shapely.get_coordinates(shapely.segmentize(a, 0.5)))
    tree = shapely.STRtree(list(getattr(b, "geoms", [b])))
    _, dist = tree.query_nearest(pts, return_distance=True, all_matches=False)
    return float(dist.max()) if len(dist) else 0.0


def compare(solidworks_dxf: Path, shop_dxf: Path, tol: float = 0.05) -> list[str]:
    """Empty when every cut curve in both files lies within ``tol`` mm of the other."""
    sw = _cut_lines(solidworks_dxf, None)
    ours = _cut_lines(shop_dxf, CUT)
    if sw.is_empty:
        return ["File flat pattern của SolidWorks không có đường cắt nào."]
    best = None
    for fx, fy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        cand = affinity.scale(sw, fx, fy, origin=(0, 0))
        d = max(_deviation(cand, ours), _deviation(ours, cand))
        best = d if best is None else min(best, d)
        if d <= tol:
            return []
    return [
        f"Flat pattern SolidWorks lệch file giao xưởng tới {best:.3f} mm (cho phép {tol:g} mm)."
    ]
