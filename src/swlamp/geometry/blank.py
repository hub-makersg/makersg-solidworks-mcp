"""Flat blank of a box part: outline, cuts, bend lines and the predicted folded size.

Flat coordinates: base centred on the origin, x towards the right wall, y towards the
back wall, viewed from the +Z side. The sheet is thickened towards −Z and every bend
folds towards +Z, so the +Z face becomes the inside of the box and the outside bottom
face sits at z = −T.

Bends are folded outermost first (lips and hems, then walls). Every bend line therefore
still lies on the unmoved, flat part of the sheet when its turn comes, so all bend
sketches can be drawn in the base plane.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from ..kfactor.table import Lookup
from ..spec.models import Lamp, Part, Side
from ..spec.rules import usable_area
from . import artwork as art
from . import patterns, tabslot
from . import text as lettering
from .bends import BendLine, BendMath
from .shapes import Circle, Cut, Loop, loops_of

CORNER_GAP = 0.3  # clearance between walls (and lips) meeting at a corner
ADJACENT = {
    "front": ("left", "right"),
    "back": ("left", "right"),
    "left": ("front", "back"),
    "right": ("front", "back"),
}


class GeometryError(ValueError):
    pass


@dataclass
class Blank:
    part: str
    thickness: float
    k: float
    radius: float
    outline: Polygon
    cuts: list[Cut]
    bends: list[BendLine]
    fixed_point: tuple[float, float]
    folded_bbox: tuple[float, float, float, float, float, float]
    outer: dict[str, float] = field(default_factory=dict)

    @property
    def flat_bbox(self) -> tuple[float, float, float, float]:
        return self.outline.bounds


@dataclass(frozen=True)
class _Frame:
    """A wall's flat frame: ``s`` along the bend line, ``u`` away from the base."""

    side: Side
    line: float  # flat coordinate of the bend line (y for front/back, x for left/right)
    s0: float
    s1: float

    def point(self, s: float, u: float) -> tuple[float, float]:
        if self.side == "front":
            return (s, self.line - u)
        if self.side == "back":
            return (s, self.line + u)
        if self.side == "left":
            return (self.line - u, s)
        return (self.line + u, s)

    def rect(self, s0: float, s1: float, u0: float, u1: float) -> Polygon:
        a, b = self.point(s0, u0), self.point(s1, u1)
        return box(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))

    def s_of_face_x(self, fx: float) -> float:
        # Seen from outside: front x → +flat x, back → −x, left → −y, right → +y.
        return -fx if self.side in ("back", "left") else fx


class _Builder:
    def __init__(self, lamp: Lamp, part: Part, lookup: Lookup) -> None:
        self.lamp, self.part = lamp, part
        self.t = lamp.thickness
        self.k, self.r = lookup.k, lookup.radius
        self.bm = BendMath(self.t, self.r, self.k)
        self.c = self.bm.inset(90)
        w, d = part.width, part.depth
        walls = part.walls
        self.edge = {
            "left": w / 2 - (self.c if "left" in walls else 0),
            "right": w / 2 - (self.c if "right" in walls else 0),
            "front": d / 2 - (self.c if "front" in walls else 0),
            "back": d / 2 - (self.c if "back" in walls else 0),
        }
        self.frames: dict[str, _Frame] = {}
        for side in walls:
            a, b = ADJACENT[side]
            if side in ("front", "back"):
                lo, hi = -self.edge["left"], self.edge["right"]
            else:
                lo, hi = -self.edge["front"], self.edge["back"]
            if a in walls:
                lo += CORNER_GAP
            if b in walls:
                hi -= CORNER_GAP
            line = {
                "front": -self.edge["front"],
                "back": self.edge["back"],
                "left": -self.edge["left"],
                "right": self.edge["right"],
            }[side]
            self.frames[side] = _Frame(side, line, lo, hi)
        self.solids: list[Polygon] = [
            box(-self.edge["left"], -self.edge["front"], self.edge["right"], self.edge["back"])
        ]
        self.voids: list[Polygon] = []
        self.bends: list[BendLine] = []
        self.cuts: list[Cut] = []
        self.tab_top = 0.0

    # -- walls, lips, hems, tabs -------------------------------------------------
    def _intrusion(self, side: str) -> float:
        wall = self.part.walls.get(side)
        if wall is None:
            return 0.0
        if wall.lip:
            return wall.lip
        if wall.hem:
            return self.r + 2 * self.t
        return self.t

    def walls(self) -> None:
        relief = self.r + self.t + 0.5
        for side, wall in self.part.walls.items():
            f = self.frames[side]
            if wall.lip:
                u_top, extra, angle, kind = wall.height - 2 * self.c, wall.lip - self.c, 90, "lip"
            elif wall.hem:
                u_top = wall.height - self.c - self.bm.inset(180)
                extra, angle, kind = wall.hem.length - self.bm.inset(180), 180, "hem"
            else:
                u_top, extra, angle, kind = wall.height - self.c, 0.0, 0, ""
            self.solids.append(f.rect(f.s0, f.s1, 0, u_top))
            a, b = ADJACENT[side]  # neighbours at the s0 and s1 ends
            self._wall_bend(side, f)
            if kind:
                lo = f.s0 + (self._intrusion(a) + CORNER_GAP if a in self.part.walls else 0)
                hi = f.s1 - (self._intrusion(b) + CORNER_GAP if b in self.part.walls else 0)
                if hi - lo < 4 * self.t:
                    raise GeometryError(
                        f"{self.part.name}.{side}: {kind} quá ngắn sau khi chừa góc."
                    )
                self.solids.append(f.rect(lo, hi, u_top, u_top + extra))
                for s_edge, s_out in ((lo, lo - self.t), (hi, hi + self.t)):
                    if abs(s_edge - (f.s0 if s_out < s_edge else f.s1)) > 1e-9:
                        self.voids.append(
                            f.rect(min(s_edge, s_out), max(s_edge, s_out), u_top - relief, u_top)
                        )
                p1, p2 = f.point(lo, u_top), f.point(hi, u_top)
                self.bends.append(BendLine(*p1, *p2, angle=angle, kind=kind, order=0))
            for tab in self.part.tabs:
                if tab.wall != side:
                    continue
                if kind:
                    raise GeometryError(
                        f"{self.part.name}.{side}: tab không đặt được trên vách có {kind}."
                    )
                length = tab.length or (tab.mating_thickness or self.t) + 2
                for at in tab.at:
                    s = f.s_of_face_x(at)
                    self.solids.append(
                        f.rect(s - tab.width / 2, s + tab.width / 2, u_top - 0.01, u_top + length)
                    )
                self.tab_top = max(self.tab_top, length)

    def _wall_bend(self, side: str, f: _Frame) -> None:
        if side in ("front", "back"):
            s_lo, s_hi = -self.edge["left"], self.edge["right"]
        else:
            s_lo, s_hi = -self.edge["front"], self.edge["back"]
        p1, p2 = f.point(s_lo, 0), f.point(s_hi, 0)
        self.bends.append(BendLine(*p1, *p2, angle=90, kind="wall", order=1))

    def corner_reliefs(self) -> None:
        h = self.r + self.t + 0.5
        walls = self.part.walls
        for ys, xs in (("front", "left"), ("front", "right"), ("back", "left"), ("back", "right")):
            if ys in walls and xs in walls:
                cx = -self.edge["left"] if xs == "left" else self.edge["right"]
                cy = -self.edge["front"] if ys == "front" else self.edge["back"]
                self.voids.append(box(cx - h, cy - h, cx + h, cy + h))

    # -- cut features ------------------------------------------------------------
    def _map(self, face: str, fx: float, fy: float) -> tuple[float, float]:
        if face == "base":
            return (fx, fy)
        f = self.frames[face]
        return f.point(f.s_of_face_x(fx), fy - self.c)

    def _map_cut(self, face: str, cut: Cut) -> Cut:
        if isinstance(cut, Circle):
            x, y = self._map(face, cut.cx, cut.cy)
            return Circle(round(x, 6), round(y, 6), cut.r)
        pts = tuple(
            (round(a, 6), round(b, 6)) for a, b in (self._map(face, x, y) for x, y in cut.points)
        )
        return Loop(pts)

    def _fits(self, face: str, poly: Polygon, what: str) -> None:
        a = usable_area(self.part, face, self.t, self.r)
        x0, y0, x1, y1 = poly.bounds
        if not a.contains(x0, y0, x1, y1):
            raise GeometryError(
                f"{self.part.name}.{face}: {what} vượt vùng cho phép "
                f"(x {a.x0:.1f}…{a.x1:.1f}, y {a.y0:.1f}…{a.y1:.1f}); bản thiết kế cần nhỏ lại hoặc dời đi."
            )

    def features(self) -> None:
        p = self.part
        for h in p.holes:
            self.cuts.append(self._map_cut(h.face, Circle(h.x, h.y, h.d / 2)))
        for pat in p.patterns:
            cells = patterns.fill(usable_area(p, pat.face, self.t, self.r), pat)
            if not cells:
                raise GeometryError(
                    f"{p.name}.{pat.face}: không còn chỗ cho hoa văn sau khi chừa lề."
                )
            self.cuts += [self._map_cut(pat.face, c) for c in cells]
        for tx in p.texts:
            try:
                polys = lettering.lettering(tx.text, tx.height, self.t, tx.font, tx.x, tx.y)
            except lettering.TextError as exc:
                raise GeometryError(f"{p.name}.{tx.face}: {exc}") from None
            self._fits(tx.face, unary_union(polys), f"chữ '{tx.text}'")
            for poly in polys:
                self.cuts += [self._map_cut(tx.face, lp) for lp in loops_of(poly)]
        for aw in p.artworks:
            try:
                polys = art.load(aw.file, aw.width, aw.x, aw.y)
            except art.ArtworkError as exc:
                raise GeometryError(f"{p.name}.{aw.face}: {exc}") from None
            self._fits(aw.face, unary_union(polys), f"hình {aw.file}")
            for poly in polys:
                self.cuts += [self._map_cut(aw.face, lp) for lp in loops_of(poly)]
        for s in p.slots:
            lp = tabslot.slot(
                s.x, s.y, s.tab_width, s.tab_thickness or self.t, s.angle, self.lamp.coat_um
            )
            self.cuts.append(self._map_cut(s.face, lp))

    # -- assembly ----------------------------------------------------------------
    def build(self) -> Blank:
        self.walls()
        self.corner_reliefs()
        outline = (
            unary_union(self.solids).difference(unary_union(self.voids))
            if self.voids
            else unary_union(self.solids)
        )
        if not isinstance(outline, Polygon) or outline.interiors:
            raise GeometryError(f"{self.part.name}: biên dạng phẳng không liền một mảnh.")
        outline = outline.simplify(0)
        self.features()
        inner = outline.buffer(-self.t)
        shapes = [c.shape() for c in self.cuts]
        for c, s in zip(self.cuts, shapes):
            if not inner.contains(s):
                where = (c.cx, c.cy) if isinstance(c, Circle) else c.points[0]
                raise GeometryError(
                    f"{self.part.name}: chi tiết cắt gần ({where[0]:.1f}, {where[1]:.1f}) cách mép < {self.t:g} mm."
                )
        if shapes:
            union = unary_union(shapes)
            if union.area < sum(s.area for s in shapes) - 1e-3:
                raise GeometryError(f"{self.part.name}: các chi tiết cắt chồng lên nhau.")
            free = outline.difference(union.buffer(1.0))
        else:
            free = outline
        base = box(-self.edge["left"], -self.edge["front"], self.edge["right"], self.edge["back"])
        fixed = base.buffer(-2 * (self.r + self.t)).intersection(free).representative_point()
        bends = sorted(self.bends, key=lambda b: (b.order, b.kind, round(b.y1, 6), round(b.x1, 6)))
        top = max([w.height for w in self.part.walls.values()], default=0.0)
        z1 = (top + self.tab_top - self.t) if self.part.walls else 0.0
        w, d = self.part.width, self.part.depth
        return Blank(
            part=self.part.name,
            thickness=self.t,
            k=self.k,
            radius=self.r,
            outline=outline,
            cuts=self.cuts,
            bends=bends,
            fixed_point=(round(fixed.x, 6), round(fixed.y, 6)),
            folded_bbox=(-w / 2, -d / 2, -self.t, w / 2, d / 2, z1),
            outer={"width": w, "depth": d, "height": top},
        )


def build_blank(lamp: Lamp, part: Part, lookup: Lookup) -> Blank:
    """Compute the flat blank for ``part`` with the K-factor and radius in ``lookup``."""
    return _Builder(lamp, part, lookup).build()
