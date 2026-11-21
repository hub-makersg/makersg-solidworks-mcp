"""Through-cut lettering with automatic stencil bridges.

Glyph outlines come from the font with fontTools and are flattened to polylines. Every
enclosed counter (the inside of O, A, D, a logo's eye...) would fall out of the sheet,
so each one gets a bridge of material connecting it to the surrounding sheet.
"""

from __future__ import annotations

import math
import os
from functools import reduce
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union

FLATNESS = 0.02  # mm, maximum chord error after scaling
DEFAULT_FONTS = ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf")


class TextError(ValueError):
    pass


def default_font() -> Path:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for name in DEFAULT_FONTS:
        if (windir / name).exists():
            return windir / name
    raise TextError(
        "Không tìm thấy font mặc định; khai báo 'font:' (đường dẫn TTF/OTF) trong spec."
    )


class _FlattenPen(BasePen):
    def __init__(self, glyphset, step: float):
        super().__init__(glyphset)
        self.step = step  # font units per segment
        self.rings: list[list[tuple[float, float]]] = []
        self._cur: list[tuple[float, float]] = []

    def _moveTo(self, pt):
        self._cur = [pt]

    def _lineTo(self, pt):
        self._cur.append(pt)

    def _segments(self, length: float) -> int:
        return max(2, min(64, int(length / self.step) + 1))

    def _curveToOne(self, p1, p2, p3):
        p0 = self._cur[-1]
        n = self._segments(math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3))
        for i in range(1, n + 1):
            t = i / n
            u = 1 - t
            self._cur.append(
                (
                    u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                    u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
                )
            )

    def _qCurveToOne(self, p1, p2):
        p0 = self._cur[-1]
        n = self._segments(math.dist(p0, p1) + math.dist(p1, p2))
        for i in range(1, n + 1):
            t = i / n
            u = 1 - t
            self._cur.append(
                (
                    u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                    u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
                )
            )

    def _closePath(self):
        if len(self._cur) >= 3:
            self.rings.append(self._cur)
        self._cur = []

    _endPath = _closePath


def _glyph_shapes(font: TTFont, text: str, step: float) -> list[Polygon]:
    glyphset = font.getGlyphSet()
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    x = 0.0
    shapes: list[Polygon] = []
    for ch in text:
        if ch == " ":
            x += hmtx["space"][0] if "space" in hmtx.metrics else font["head"].unitsPerEm / 3
            continue
        name = cmap.get(ord(ch))
        if name is None:
            raise TextError(f"Font không có ký tự {ch!r}.")
        pen = _FlattenPen(glyphset, step)
        glyphset[name].draw(pen)
        polys = [Polygon([(px + x, py) for px, py in ring]).buffer(0) for ring in pen.rings]
        if polys:
            shapes.append(reduce(lambda a, b: a.symmetric_difference(b), polys))
        x += hmtx[name][0]
    return shapes


def _parts(geom) -> list[Polygon]:
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def _bridge(glyph: Polygon, width: float) -> Polygon | MultiPolygon:
    """Cut away a vertical strip above every counter so it stays joined to the sheet."""
    cut = glyph
    top = glyph.bounds[3] + width
    for ring in glyph.interiors:
        counter = Polygon(ring)
        cx = counter.centroid.x
        strip = box(cx - width / 2, counter.centroid.y, cx + width / 2, top)
        cut = cut.difference(strip)
    return cut


def lettering(
    text: str,
    cap_height: float,
    thickness: float,
    font_path: str | Path | None = None,
    x: float = 0.0,
    y: float = 0.0,
) -> list[Polygon]:
    """Cut regions for ``text`` centred on (x, y), cap height ``cap_height`` mm.

    Raises :class:`TextError` when strokes or bridges would be thinner than the sheet.
    """
    path = Path(font_path) if font_path else default_font()
    font = TTFont(str(path))
    upm = font["head"].unitsPerEm
    cap = getattr(font.get("OS/2"), "sCapHeight", 0) or 0.7 * upm
    scale = cap_height / cap
    glyphs = _glyph_shapes(font, text, FLATNESS / scale * 4)
    if not glyphs:
        raise TextError("Chuỗi chữ rỗng.")
    bridge = max(thickness, 0.8)
    pieces: list[Polygon] = []
    for g in glyphs:
        for poly in _parts(g):
            pieces += _parts(_bridge(poly, bridge / scale))
    merged = unary_union([affinity.scale(p, scale, scale, origin=(0, 0)) for p in pieces])
    minx, miny, maxx, maxy = merged.bounds
    merged = affinity.translate(merged, x - (minx + maxx) / 2, y - (miny + maxy) / 2)
    out = [p for p in _parts(merged) if p.area > 1e-6]
    if any(p.interiors for p in out):
        raise TextError(f"Không nối cầu được cho mọi lõi chữ của '{text}'; thử font khác.")
    min_size = _min_cap_height(cap_height, out, thickness)
    if min_size:
        raise TextError(
            f"Nét chữ '{text}' mảnh hơn độ dày tấm {thickness:g} mm; "
            f"cần cỡ chữ tối thiểu khoảng {min_size:.0f} mm."
        )
    return out


def _min_cap_height(cap_height: float, polys: list[Polygon], thickness: float) -> float:
    """0 when every stroke survives an opening by the sheet thickness, else a suggested size."""
    area = sum(p.area for p in polys)
    opened = sum(p.buffer(-thickness / 2).buffer(thickness / 2).area for p in polys)
    if area and opened / area >= 0.85:
        return 0.0
    ratio = opened / area if area else 0.0
    return cap_height * max(1.5, 1.0 / max(ratio, 0.1))
