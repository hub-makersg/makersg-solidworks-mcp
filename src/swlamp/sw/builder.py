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
    hits: list[tuple[float, float, float] | None] = field(default_factory=list)  # mm
    doc: object = field(default=None, repr=False, compare=False)  # open IModelDoc2


class BuildError(RuntimeError):
    pass


def open_titles(sw: Sw) -> list[str]:
    docs = sw.app.GetDocuments() or ()
    return [sw.typed(d, "IModelDoc2").GetTitle() for d in docs]


def ensure_not_open(sw: Sw, title: str) -> None:
    """SolidWorks cannot open two documents with the same name; it hands back the open one."""
    if any(Path(t).stem.lower() == title.lower() for t in open_titles(sw)):
        raise BuildError(f"SolidWorks đang mở một tài liệu tên '{title}'; đóng nó rồi thử lại.")


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
            f.Select2(False, 0)
            d.doc.BlankSketch()
    d.doc.ClearSelection2(True)


def ray_hits(sw: Sw, doc, checks) -> list[tuple[float, float, float] | None]:
    """First point where each checkpoint's ray meets the folded body (mm), or None.

    One ``RayIntersections`` call covers every ray, so this costs a few COM round trips
    whatever the part's complexity.
    """
    if not checks:
        return []
    import pythoncom
    from win32com.client import VARIANT

    part = sw.typed(doc, "IPartDoc")
    bodies = list(part.GetBodies2(sw.const.swSolidBody, True) or ())
    if not bodies:
        return [None] * len(checks)
    pts = [c * MM for cp in checks for c in cp.origin]
    dirs = [c for cp in checks for c in cp.direction]
    model = sw.typed(doc, "IModelDoc2")
    options = sw.const.swRayPtsOptsNORMALS | sw.const.swRayPtsOptsENTRY_EXIT
    count = model.RayIntersections(
        VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, bodies),
        VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, pts),
        VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, dirs),
        options,
        0.0,
        0.0,
    )
    best: list[tuple[float, tuple[float, float, float]] | None] = [None] * len(checks)
    if count:
        flat = model.GetRayIntersectionsPoints() or ()
        for i in range(0, len(flat), 9):  # body, ray, type, x, y, z, nx, ny, nz
            ray = int(flat[i + 1])
            hit = tuple(round(v / MM, 4) for v in flat[i + 3 : i + 6])
            o = checks[ray].origin
            dist = sum((a - b) ** 2 for a, b in zip(hit, o, strict=True))
            if best[ray] is None or dist < best[ray][0]:
                best[ray] = (dist, hit)
    return [b[1] if b else None for b in best]


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
    ensure_not_open(sw, path.stem)
    template = sw.app.GetUserPreferenceStringValue(sw.const.swDefaultTemplatePart)
    raw = sw.app.NewDocument(template, 0, 0, 0)
    if raw is None:
        raise BuildError("SolidWorks không tạo được part mới.")
    d = _Doc(sw, raw)
    try:
        return _build_into(sw, d, blank, path)
    except BaseException:
        sw.app.CloseDoc(d.doc.GetTitle())
        raise


def _build_into(sw: Sw, d: _Doc, blank: Blank, path: Path) -> BuildResult:
    view = sw.typed(d.doc.ActiveView, "IModelView")
    # Batch mode for out-of-process callers: no redraws, no tree refresh, sketch
    # entities added straight to the database.
    sw.app.CommandInProgress = True
    view.EnableGraphicsUpdate = False
    d.fm.EnableFeatureTree = False
    d.sk.DisplayWhenAdded = False
    try:
        _base_flange(d, blank)
        errors = [e for e in (_bend(d, blank, b) for b in blank.bends) if e]
        _hide_sketches(d)
    finally:
        d.sk.DisplayWhenAdded = True
        d.fm.EnableFeatureTree = True
        view.EnableGraphicsUpdate = True
        sw.app.CommandInProgress = False
    ok, err, _warn = d.ext.SaveAs3(str(path), 0, sw.const.swSaveAsOptions_Silent, None, None, 0, 0)
    if not ok:
        raise BuildError(f"Không lưu được part {path} (mã lỗi {err}).")
    bbox, bodies = body_bbox(sw, d.doc)
    errors += feature_errors(sw, d.doc)
    return BuildResult(
        title=d.doc.GetTitle(),
        path=str(path),
        errors=errors,
        bbox=bbox,
        bodies=bodies,
        hits=ray_hits(sw, d.doc, blank.checks),
        doc=d.doc,
    )


def close(sw: Sw, title: str) -> None:
    sw.app.CloseDoc(title)
