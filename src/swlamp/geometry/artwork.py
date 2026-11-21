"""Load 2D artwork (DXF or SVG) as cut polygons scaled to a width and centred on a point."""

from __future__ import annotations

from functools import reduce
from pathlib import Path

import ezdxf
from ezdxf import bbox as ezbbox
from ezdxf import path as ezpath
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon

FLATNESS = 0.02  # mm, chord error for DXF curves
SEGMENT_MM = 0.5  # chord length for SVG curves: error ≤ 0.02 mm for radii ≥ 1.6 mm


class ArtworkError(ValueError):
    pass


def _even_odd(rings: list[list[tuple[float, float]]]) -> list[Polygon]:
    polys = [Polygon(r).buffer(0) for r in rings if len(r) >= 3]
    polys = [p for p in polys if not p.is_empty]
    if not polys:
        raise ArtworkError("Hình không có đường kín nào để cắt.")
    geom = reduce(lambda a, b: a.symmetric_difference(b), polys)
    return list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]


def _dxf_rings(doc, flatness: float) -> list[list[tuple[float, float]]]:
    rings = []
    for entity in doc.modelspace():
        try:
            p = ezpath.make_path(entity)
        except (TypeError, ValueError):
            continue
        for sub in p.sub_paths():
            pts = [(v.x, v.y) for v in sub.flattening(flatness)]
            if len(pts) >= 3 and (sub.is_closed or pts[0] == pts[-1]):
                rings.append(pts)
    return rings


def _svg_rings(svg, step: float) -> list[list[tuple[float, float]]]:
    """Flatten every SVG shape with chords no longer than ``step`` (SVG units)."""
    from svgelements import Close, Line, Move, Shape
    from svgelements import Path as SvgPath

    rings: list[list[tuple[float, float]]] = []
    for element in svg.elements():
        if not isinstance(element, Shape):
            continue
        path = SvgPath(element)
        current: list[tuple[float, float]] = []
        for seg in path.segments():
            if isinstance(seg, Move):
                if len(current) >= 3:
                    rings.append(current)
                current = [(seg.end.x, -seg.end.y)]
                continue
            if isinstance(seg, Close):
                if len(current) >= 3:
                    rings.append(current)
                current = []
                continue
            n = 1 if isinstance(seg, Line) else max(2, int(seg.length(error=1e-4) / step) + 1)
            for i in range(1, n + 1):
                pt = seg.point(i / n)
                current.append((pt.x, -pt.y))  # SVG y points down
        if len(current) >= 3:
            rings.append(current)
    return rings


def load(file: str | Path, width: float, x: float = 0.0, y: float = 0.0) -> list[Polygon]:
    path = Path(file)
    if not path.exists():
        raise ArtworkError(f"Không thấy file hình: {path}")
    suffix = path.suffix.lower()
    if suffix == ".dxf":
        doc = ezdxf.readfile(path)
        ext = ezbbox.extents(doc.modelspace())
        rings = _dxf_rings(doc, FLATNESS * ext.size.x / width)
    elif suffix == ".svg":
        from svgelements import SVG

        svg = SVG.parse(str(path))
        x0, _, x1, _ = svg.bbox()
        rings = _svg_rings(svg, SEGMENT_MM * (x1 - x0) / width)
    else:
        raise ArtworkError(f"Chỉ nhận DXF hoặc SVG, không nhận '{suffix}'.")
    polys = _even_odd(rings)
    minx = min(p.bounds[0] for p in polys)
    maxx = max(p.bounds[2] for p in polys)
    miny = min(p.bounds[1] for p in polys)
    maxy = max(p.bounds[3] for p in polys)
    s = width / (maxx - minx)
    out = []
    for p in polys:
        q = affinity.scale(p, s, s, origin=(minx, miny))
        q = affinity.translate(q, x - width / 2 - minx, y - (maxy - miny) * s / 2 - miny)
        out.append(q)
    islands = [p for p in out if p.interiors]
    if islands:
        raise ArtworkError(
            f"Hình {path.name} có {sum(len(p.interiors) for p in islands)} đảo kín sẽ rơi ra khi cắt; "
            "thêm cầu nối trong file hình rồi thử lại."
        )
    return out
