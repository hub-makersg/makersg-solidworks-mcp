"""Run one order end to end: spec → flat blanks → SolidWorks → checked shop files.

Nothing reaches the order folder as a shop DXF unless the folded part SolidWorks built
matches the spec's outside dimensions within 0.05 mm and the SolidWorks flat pattern
matches the DXF. Every SolidWorks document the run opened is closed again.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..config import output_root
from ..dxfcheck.compare import compare
from ..dxfcheck.validate import validate
from ..dxfcheck.write import write_dxf
from ..geometry.blank import Blank, GeometryError, build_blank
from ..geometry.preview import render
from ..kfactor.table import Key, KTable, Lookup
from ..paths import Guard, new_order_dir
from ..spec.merge import SpecError, load_yaml, resolve
from ..spec.models import Lamp, Order, PrintedPart
from ..spec.rules import check
from .summary import BendReport, OrderReport, PartReport, write

DIM_TOL = 0.05  # mm, folded body vs spec outside dimensions


@dataclass
class PartJob:
    blank: Blank
    sldprt: Path
    sw_flat: Path
    meshes: list[Path]
    image: Path


@dataclass
class PrintedJob:
    part: PrintedPart
    source: Path
    copy: Path
    meshes: list[Path]


@dataclass
class PartOutcome:
    bbox: tuple[float, ...]
    errors: list[str] = field(default_factory=list)


class Steps(Protocol):
    """The SolidWorks side of an order (a fake stands in for it in offline tests)."""

    def produce(self, parts: list[PartJob], printed: list[PrintedJob]) -> list[PartOutcome]: ...


class SolidWorksSteps:
    def __init__(self, worker: Any) -> None:
        self.worker = worker

    def produce(self, parts: list[PartJob], printed: list[PrintedJob]) -> list[PartOutcome]:
        from ..sw import builder, equations, export

        def job(sw):
            opened: list[str] = []
            outcomes: list[PartOutcome] = []
            sw.quiet()
            try:
                for pj in parts:
                    r = builder.build(sw, pj.blank, pj.sldprt)
                    opened.append(r.title)
                    outcomes.append(PartOutcome(r.bbox, list(r.errors)))
                    if r.errors:
                        continue
                    export.flat_dxf(sw, r.doc, pj.sw_flat)
                    for m in pj.meshes:
                        export.mesh(sw, r.doc, m)
                    export.screenshot(sw, r.doc, pj.image)
                for job_ in printed:
                    model = equations.open_copy(sw, job_.source, job_.copy)
                    opened.append(model.GetTitle())
                    errors = equations.apply(sw, model, dict(job_.part.vars))
                    if errors:
                        raise RuntimeError(f"{job_.part.name}: rebuild lỗi: {'; '.join(errors)}")
                    model.Save3(1, 0, 0)
                    for m in job_.meshes:
                        export.mesh(sw, model, m)
                return outcomes
            finally:
                for title in opened:
                    builder.close(sw, title)
                sw.restore()

        return self.worker.run(job, timeout=1800)


def _within(measured: tuple[float, ...], predicted: tuple[float, ...]) -> list[str]:
    names = ("x min", "y min", "z min", "x max", "y max", "z max")
    return [
        f"{n}: SolidWorks {m:.3f} mm, spec {p:.3f} mm"
        for n, m, p in zip(names, measured, predicted, strict=True)
        if abs(m - p) > DIM_TOL
    ]


def _load(value: dict | str | Path | None) -> dict | None:
    if value is None or isinstance(value, dict):
        return value
    return load_yaml(value)


def run_order(
    template: dict | str | Path,
    order: dict | str | Path | None,
    steps: Steps,
    table: KTable | None = None,
    root: Path | None = None,
) -> OrderReport:
    table = table or KTable()
    tpl = _load(template)
    order_data = _load(order) or {"order_id": "draft"}
    order_obj = Order.model_validate(order_data)
    lamp: Lamp = resolve(tpl, order_obj)
    key = Key(lamp.material, lamp.thickness, lamp.shop, lamp.die_v)
    lookup: Lookup = table.lookup(key)
    check(lamp, lookup.radius, key.die)
    blanks = [build_blank(lamp, p, lookup) for p in lamp.parts]

    folder = new_order_dir(root or output_root(), order_obj.order_id)
    guard = Guard(folder)
    oid = order_obj.order_id
    report = OrderReport(oid, str(folder), lamp.material, lamp.thickness)
    check_dir = guard.path("_check")
    check_dir.mkdir()
    part_jobs = [
        PartJob(
            blank=b,
            sldprt=guard.path(f"{b.part}__{oid}.SLDPRT"),
            sw_flat=check_dir / f"{b.part}__{oid}.sw.dxf",
            meshes=[guard.path(f"{b.part}__{oid}.3mf"), guard.path(f"{b.part}__{oid}.stl")],
            image=guard.path(f"{b.part}__{oid}.png"),
        )
        for b in blanks
    ]
    printed_jobs = []
    for pp in lamp.printed_parts:
        src = Path(pp.model)
        printed_jobs.append(
            PrintedJob(
                part=pp,
                source=src,
                copy=guard.path(f"{src.stem}__{oid}{src.suffix}"),
                meshes=[guard.path(f"{pp.name}__{oid}.3mf"), guard.path(f"{pp.name}__{oid}.stl")],
            )
        )
    for b in blanks:
        x0, y0, x1, y1 = b.flat_bbox
        report.parts.append(
            PartReport(
                name=b.part,
                k=b.k,
                radius=b.radius,
                bends=[BendReport(x.kind, x.angle, lookup.status_for(x.angle)) for x in b.bends],
                flat_size=(round(x1 - x0, 3), round(y1 - y0, 3)),
                folded_bbox=tuple(round(v, 3) for v in b.folded_bbox),
            )
        )
    try:
        outcomes = steps.produce(part_jobs, printed_jobs)
        for pj, outcome, pr in zip(part_jobs, outcomes, report.parts, strict=True):
            pr.measured_bbox = tuple(outcome.bbox)
            report.errors += [f"{pj.blank.part}: {e}" for e in outcome.errors]
            if not outcome.errors:
                off = _within(outcome.bbox, pj.blank.folded_bbox)
                report.errors += [f"{pj.blank.part}: kích thước dạng gập lệch — {o}" for o in off]
        if not report.errors:
            for pj, pr in zip(part_jobs, report.parts, strict=True):
                dxf = write_dxf(pj.blank, guard.path(f"{pj.blank.part}__{oid}.dxf"))
                problems = validate(dxf, pj.blank) + compare(pj.sw_flat, dxf)
                if problems:
                    report.errors += [f"{pj.blank.part}: {p}" for p in problems]
                    continue
                preview = render(pj.blank, guard.path(f"{pj.blank.part}__{oid}.flat.png"))
                pr.files = [dxf.name, pj.sldprt.name, *(m.name for m in pj.meshes)]
                report.images += [str(pj.image), str(preview)]
            report.printed = [m.name for j in printed_jobs for m in j.meshes]
    except Exception as exc:  # reported in the summary; the order folder keeps no shop DXF
        report.errors.append(str(exc))
    finally:
        shutil.rmtree(check_dir, ignore_errors=True)
    if report.errors:
        report.status = "error"
        for dxf in folder.glob("*.dxf"):
            dxf.unlink()
        for pr in report.parts:
            pr.files = []
    write(report, folder)
    return report


__all__ = [
    "GeometryError",
    "OrderReport",
    "SolidWorksSteps",
    "SpecError",
    "Steps",
    "run_order",
]
