"""Build a sheet-metal part in SolidWorks from a flat blank.

The part is one base flange drawn from the flat outline with every cut inside it, then
one sketched bend per bend line, outermost bends first so each bend sketch still lies in
the base plane. Facts found on SolidWorks 2025 SP5:

* features go through ``FeatureManager.CreateDefinition`` + ``CreateFeature``
  (``swFmBaseFlange``, ``swFmSketchBend``);
* a sketched bend ignores the part's K-factor unless its own custom bend allowance is set
  (it defaults to K = 0.5), so every bend gets the calibrated K explicitly;
* a sketched bend needs both its sketch and the fixed face selected before
  ``CreateFeature``;
* square corner reliefs are required where two walls meet, otherwise the second bend fails.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from ..geometry.blank import Blank
from ..geometry.shapes import Circle, Loop
from .connection import Sw

MM = 0.001


@dataclass(frozen=True)
class Op:
    kind: str  # "base_flange" or "bend"
    detail: tuple


def plan_ops(blank: Blank) -> list[Op]:
    """The deterministic sequence of SolidWorks operations for ``blank``."""
    ops = [Op("base_flange", (blank.thickness, blank.radius, blank.k, len(blank.cuts)))]
    for b in blank.bends:
        ops.append(Op("bend", (b.kind, b.angle, b.x1, b.y1, b.x2, b.y2, b.up)))
    return ops


@dataclass
class BuildResult:
    title: str
    path: str
    errors: list[str] = field(default_factory=list)
    bbox: tuple[float, ...] = ()  # mm: x0, y0, z0, x1, y1, z1 of the folded body
    bodies: int = 0
    doc: object = field(default=None, repr=False, compare=False)  # open IModelDoc2


class BuildError(RuntimeError):
    pass


def open_titles(sw: Sw) -> list[str]:
    docs = sw.app.GetDocuments() or ()
    return [sw.typed(d, "IModelDoc2").GetTitle() for d in docs]


def _title_of(path: Path) -> str:
    return path.stem


class _Doc:
    def __init__(self, sw: Sw, doc) -> None:
        self.sw = sw
        self.doc = sw.typed(doc, "IModelDoc2")
        self.ext = sw.typed(self.doc.Extension, "IModelDocExtension")
        self.sk = sw.typed(self.doc.SketchManager, "ISketchManager")
        self.fm = sw.typed(self.doc.FeatureManager, "IFeatureManager")
        self.c = sw.const

    def features(self):
        f = self.doc.FirstFeature()
        while f is not None:
            f = self.sw.typed(f, "IFeature")
            yield f
            f = f.GetNextFeature()

    def last(self, type_name: str):
        hit = None
        for f in self.features():
            if f.GetTypeName2() == type_name:
                hit = f
        return hit

    def begin_sketch(self, on_face: tuple[float, float] | None) -> None:
        self.doc.ClearSelection2(True)
        if on_face is None:
            ok = self.ext.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
        else:
            ok = self.ext.SelectByID2(
                "", "FACE", on_face[0] * MM, on_face[1] * MM, 0, False, 0, None, 0
            )
        if not ok:
            raise BuildError("Không chọn được mặt phẳng để vẽ sketch.")
        self.sk.InsertSketch(True)
        self.sk.AddToDB = True

    def end_sketch(self):
        self.sk.AddToDB = False
        self.sk.InsertSketch(True)
        return self.last("ProfileFeature")

    def ring(self, pts) -> None:
        n = len(pts)
        for i in range(n):
            (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
            self.sk.CreateLine(x1 * MM, y1 * MM, 0, x2 * MM, y2 * MM, 0)

    def allowance(self, k: float):
        cba = self.sw.typed(self.fm.CreateCustomBendAllowance(), "ICustomBendAllowance")
        cba.Type = self.c.swBendAllowanceKFactor
        cba.KFactor = k
        return cba


def _base_flange(d: _Doc, blank: Blank) -> None:
    d.begin_sketch(None)
    d.ring(list(blank.outline.exterior.coords)[:-1])
    for cut in blank.cuts:
        if isinstance(cut, Circle):
            d.sk.CreateCircleByRadius(cut.cx * MM, cut.cy * MM, 0, cut.r * MM)
        elif isinstance(cut, Loop):
            d.ring(cut.points)
    sketch = d.end_sketch()
    d.doc.ClearSelection2(True)
    sketch.Select2(False, 0)
    fd = d.sw.typed(d.fm.CreateDefinition(d.c.swFmBaseFlange), "IBaseFlangeFeatureData")
    fd.Initialize(False, True, d.allowance(blank.k), False, 0, True, 0.5, 0.0, 0.0)
    fd.UseGaugeTable = False
    fd.Thickness = blank.thickness * MM
    fd.BendRadius = blank.radius * MM
    fd.ReverseThickness = False
    if d.fm.CreateFeature(fd) is None:
        raise BuildError("SolidWorks không tạo được base flange từ bản phẳng.")


def _bend(d: _Doc, blank: Blank, bend) -> str | None:
    fx, fy = blank.fixed_point
    d.begin_sketch((fx, fy))
    d.sk.CreateLine(bend.x1 * MM, bend.y1 * MM, 0, bend.x2 * MM, bend.y2 * MM, 0)
    sketch = d.end_sketch()
    d.doc.ClearSelection2(True)
    sketch.Select2(False, 0)
    d.ext.SelectByID2("", "FACE", fx * MM, fy * MM, 0, True, 0, None, 0)
    data = d.sw.typed(d.fm.CreateDefinition(d.c.swFmSketchBend), "ISketchedBendFeatureData")
    data.BendAngle = math.radians(bend.angle)
    data.UseDefaultBendRadius = False
    data.BendRadius = blank.radius * MM
    data.PositionType = d.c.swFlangePositionTypeBendCenterLine
    data.ReverseDirection = not bend.up
    data.UseDefaultBendAllowance = False
    data.SetCustomBendAllowance(d.allowance(blank.k))
    if d.fm.CreateFeature(data) is None:
        return (
            f"nếp {bend.kind} {bend.angle:g}° tại ({bend.x1:.1f}, {bend.y1:.1f})–"
            f"({bend.x2:.1f}, {bend.y2:.1f}) không gập được"
        )
    return None


def _hide_sketches(d: _Doc) -> None:
    for f in d.features():
        if f.GetTypeName2() == "ProfileFeature":
            d.doc.ClearSelection2(True)
            f.Select2(False, 0)
            d.doc.BlankSketch()
    d.doc.ClearSelection2(True)


def body_bbox(sw: Sw, doc) -> tuple[tuple[float, ...], int]:
    part = sw.typed(doc, "IPartDoc")
    bodies = part.GetBodies2(sw.const.swSolidBody, True) or ()
    boxes = [sw.typed(b, "IBody2").GetBodyBox() for b in bodies]
    if not boxes:
        return (), 0
    lo = [min(b[i] for b in boxes) / MM for i in range(3)]
    hi = [max(b[i + 3] for b in boxes) / MM for i in range(3)]
    return tuple(round(v, 4) for v in (*lo, *hi)), len(boxes)


def feature_errors(sw: Sw, doc) -> list[str]:
    d = _Doc(sw, doc)
    errors = []
    for f in d.features():
        code = f.GetErrorCode2()
        code = code[0] if isinstance(code, tuple) else code
        if code:
            errors.append(f"{f.Name}: mã lỗi {code}")
    return errors


def build(sw: Sw, blank: Blank, path: Path) -> BuildResult:
    """Create, save and keep open the part for ``blank`` at ``path`` (order-unique name)."""
    title = _title_of(path)
    if any(t.lower().startswith(title.lower()) for t in open_titles(sw)):
        raise BuildError(f"SolidWorks đang mở một tài liệu tên '{title}'; đóng nó rồi thử lại.")
    template = sw.app.GetUserPreferenceStringValue(sw.const.swDefaultTemplatePart)
    raw = sw.app.NewDocument(template, 0, 0, 0)
    if raw is None:
        raise BuildError("SolidWorks không tạo được part mới.")
    d = _Doc(sw, raw)
    view = sw.typed(d.doc.ActiveView, "IModelView")
    sw.app.CommandInProgress = True  # fewer redraws for out-of-process callers
    view.EnableGraphicsUpdate = False
    try:
        _base_flange(d, blank)
        errors = [e for e in (_bend(d, blank, b) for b in blank.bends) if e]
    finally:
        view.EnableGraphicsUpdate = True
        sw.app.CommandInProgress = False
    _hide_sketches(d)
    d.doc.ShowNamedView2("*Isometric", 7)
    d.doc.ViewZoomtofit2()
    ok, err, _warn = d.ext.SaveAs3(str(path), 0, sw.const.swSaveAsOptions_Silent, None, None, 0, 0)
    if not ok:
        raise BuildError(f"Không lưu được part {path} (mã lỗi {err}).")
    bbox, bodies = body_bbox(sw, d.doc)
    errors += feature_errors(sw, d.doc)
    return BuildResult(
        title=d.doc.GetTitle(), path=str(path), errors=errors, bbox=bbox, bodies=bodies, doc=d.doc
    )


def close(sw: Sw, title: str) -> None:
    sw.app.CloseDoc(title)
