"""Manufacturing rules checked before anything is built.

Sources: Protolabs / Hubs sheet-metal guides and SendCutSend ordering rules (flange ≥ 4T,
features ≥ 2T + R from the bend tangent, holes, webs and bridges ≥ 1T).
"""

from __future__ import annotations

from dataclasses import dataclass

from .merge import SpecError
from .models import FaceName, Lamp, Part


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    def contains(self, x0: float, y0: float, x1: float, y1: float) -> bool:
        eps = 1e-9
        return (
            x0 >= self.x0 - eps
            and y0 >= self.y0 - eps
            and x1 <= self.x1 + eps
            and y1 <= self.y1 + eps
        )


def min_flange(thickness: float, radius: float, die: float) -> float:
    return max(4 * thickness, die / 2 + thickness + radius)


def bend_keepout(thickness: float, radius: float) -> float:
    """Distance from the outside surface that features must keep clear of a bend."""
    return (radius + thickness) + (2 * thickness + radius)


def wall_length(part: Part, side: str) -> float:
    return part.width if side in ("front", "back") else part.depth


def usable_area(part: Part, face: FaceName, thickness: float, radius: float) -> Rect:
    """Region of a face where cut features may go, in face-local coordinates."""
    keep = bend_keepout(thickness, radius)
    edge = thickness
    if face == "base":

        def lim(side: str) -> float:
            return keep if side in part.walls else edge

        return Rect(
            -part.width / 2 + lim("left"),
            -part.depth / 2 + lim("front"),
            part.width / 2 - lim("right"),
            part.depth / 2 - lim("back"),
        )
    wall = part.walls[face]
    top = keep if (wall.lip or wall.hem) else edge
    half = wall_length(part, face) / 2 - 3 * thickness
    return Rect(-half, keep, half, wall.height - top)


def _check_part(part: Part, t: float, radius: float, flange: float, problems: list[str]) -> None:
    def need(ok: bool, msg: str) -> None:
        if not ok:
            problems.append(msg)

    p = part.name
    faces = {"base", *part.walls}
    for side, wall in part.walls.items():
        need(
            wall.height >= flange,
            f"{p}.{side}: vách cao {wall.height:g} < tối thiểu {flange:.2f} mm",
        )
        if wall.lip is not None:
            need(
                wall.lip >= flange,
                f"{p}.{side}: mép gập {wall.lip:g} < tối thiểu {flange:.2f} mm",
            )
        if wall.hem is not None:
            need(
                wall.hem.kind == "open",
                f"{p}.{side}: hem kín không được hỗ trợ (nhiều xưởng chỉ chấn tới 120–130°); "
                "dùng open hem hoặc hỏi xưởng xác nhận",
            )
            need(
                wall.hem.length >= flange,
                f"{p}.{side}: hem dài {wall.hem.length:g} < tối thiểu {flange:.2f} mm",
            )
            need(wall.lip is None, f"{p}.{side}: một vách không thể có cả mép gập và hem")

    def on_face(face: str, what: str) -> bool:
        if face not in faces:
            problems.append(f"{p}: {what} nằm trên mặt '{face}' nhưng part không có mặt đó")
            return False
        return True

    def inside(face: str, what: str, x0: float, y0: float, x1: float, y1: float) -> None:
        if not on_face(face, what):
            return
        area = usable_area(part, face, t, radius)
        need(
            area.contains(x0, y0, x1, y1),
            f"{p}.{face}: {what} chạm dải cấm quanh nếp gập hoặc mép "
            f"(vùng cho phép x {area.x0:.1f}…{area.x1:.1f}, y {area.y0:.1f}…{area.y1:.1f})",
        )

    for h in part.holes:
        need(h.d >= t, f"{p}: lỗ Ø{h.d:g} nhỏ hơn độ dày {t:g} mm")
        r = h.d / 2
        inside(h.face, f"lỗ Ø{h.d:g} tại ({h.x:g}, {h.y:g})", h.x - r, h.y - r, h.x + r, h.y + r)
    for pat in part.patterns:
        need(pat.size >= t, f"{p}: hoa văn cỡ {pat.size:g} nhỏ hơn độ dày {t:g} mm")
        need(pat.web >= t, f"{p}: vách giữa lỗ hoa văn {pat.web:g} nhỏ hơn độ dày {t:g} mm")
        on_face(pat.face, "hoa văn")
    for tx in part.texts:
        on_face(tx.face, f"chữ '{tx.text}'")
    for art in part.artworks:
        on_face(art.face, f"hình {art.file}")
    for tab in part.tabs:
        need(
            tab.wall in part.walls,
            f"{p}: tab trên vách '{tab.wall}' nhưng part không có vách đó",
        )
        need(
            tab.width >= max(2 * t, 3.2),
            f"{p}: tab rộng {tab.width:g} < tối thiểu {max(2 * t, 3.2):.1f} mm",
        )
        length = tab.effective_length(t)
        need(length <= 5 * tab.width, f"{p}: tab dài {length:g} vượt 5 × bề rộng")
    for s in part.slots:
        half_w = s.tab_width / 2 + 0.5
        half_h = s.effective_thickness(t) / 2 + 0.5
        hx, hy = (half_w, half_h) if s.angle == 0 else (half_h, half_w)
        inside(s.face, f"khe tại ({s.x:g}, {s.y:g})", s.x - hx, s.y - hy, s.x + hx, s.y + hy)


def check(lamp: Lamp, radius: float, die: float) -> None:
    """Raise :class:`SpecError` listing every rule the spec breaks."""
    problems: list[str] = []
    flange = min_flange(lamp.thickness, radius, die)
    for part in lamp.parts:
        _check_part(part, lamp.thickness, radius, flange, problems)
    if problems:
        raise SpecError("Spec vi phạm luật gia công:\n- " + "\n- ".join(problems))
