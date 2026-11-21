"""Order pipeline failure paths and printed parts, with SolidWorks faked at its boundary."""

from pathlib import Path

import ezdxf
import pytest

from swlamp.dxfcheck.write import write_dxf
from swlamp.kfactor.table import KTable
from swlamp.order.pipeline import PartOutcome, run_order
from swlamp.spec.merge import SpecError

TEMPLATE = {
    "name": "t",
    "material": "steel",
    "thickness": 1.0,
    "parts": [
        {
            "name": "tray",
            "width": 120,
            "depth": 80,
            "walls": {"front": {"height": 30}, "back": {"height": 30}},
            "holes": [{"x": 0, "y": 0, "d": 20}],
        }
    ],
}


class Fake:
    """Writes what SolidWorks would; ``shift_hole`` moves the hole in its flat export."""

    def __init__(self, shift_hole=0.0, errors=None, raise_exc=None):
        self.shift_hole, self.errors, self.raise_exc = shift_hole, errors or [], raise_exc
        self.printed = []

    def produce(self, parts, printed):
        if self.raise_exc:
            raise self.raise_exc
        out = []
        for pj in parts:
            doc = ezdxf.new("R2000", setup=True)
            msp = doc.modelspace()
            for e in ezdxf.readfile(write_dxf(pj.blank, pj.sw_flat)).modelspace():
                if e.dxftype() == "CIRCLE":
                    c = e.dxf.center
                    msp.add_circle((c.x + self.shift_hole, c.y), e.dxf.radius)
                elif e.dxf.layer == "CUT":
                    msp.add_foreign_entity(e.copy())
                else:
                    msp.add_line(e.dxf.start, e.dxf.end, dxfattribs={"linetype": "DASHED"})
            doc.saveas(pj.sw_flat)
            for f in (pj.sldprt, *pj.meshes, pj.image):
                f.write_bytes(b"x")
            out.append(PartOutcome(tuple(pj.blank.folded_bbox), list(self.errors)))
        for job in printed:
            self.printed.append(job)
            for m in job.meshes:
                m.write_bytes(b"x")
        return out


def run(tmp_path, steps, template=TEMPLATE, order=None):
    return run_order(
        template, order or {"order_id": "o1"}, steps, KTable(tmp_path / "k.json"), tmp_path / "out"
    )


def test_flat_pattern_mismatch_fails_without_dxf(tmp_path):
    report = run(tmp_path, Fake(shift_hole=0.2))
    assert report.status == "error"
    assert any("lệch file giao xưởng" in e for e in report.errors)
    assert list(Path(report.folder).glob("*.dxf")) == []


def test_solidworks_build_error_fails_without_dxf(tmp_path):
    report = run(tmp_path, Fake(errors=["nếp wall 90° không gập được"]))
    assert report.status == "error"
    assert any("không gập được" in e for e in report.errors)
    assert list(Path(report.folder).glob("*.dxf")) == []


def test_solidworks_exception_is_reported_and_check_dir_removed(tmp_path):
    report = run(tmp_path, Fake(raise_exc=RuntimeError("SolidWorks đang bận")))
    assert report.status == "error"
    assert "SolidWorks đang bận" in report.errors
    assert not (Path(report.folder) / "_check").exists()
    assert (Path(report.folder) / "summary.md").exists()


def test_printed_parts_get_copies_named_per_part(tmp_path):
    model = tmp_path / "clip.SLDPRT"
    model.write_bytes(b"model")
    template = {
        **TEMPLATE,
        "printed_parts": [
            {"name": "clip_a", "model": str(model), "vars": {"ord_w": 10}},
            {"name": "clip_b", "model": str(model), "vars": {"ord_w": 12}},
        ],
    }
    fake = Fake()
    report = run(tmp_path, fake, template)
    assert report.status == "ok", report.errors
    copies = [j.copy for j in fake.printed]
    assert [c.name for c in copies] == ["clip_a__o1.SLDPRT", "clip_b__o1.SLDPRT"]
    assert all(c.parent == Path(report.folder).resolve() for c in copies)
    assert report.printed == [
        "clip_a__o1.3mf",
        "clip_a__o1.stl",
        "clip_b__o1.3mf",
        "clip_b__o1.stl",
    ]
    assert model.read_bytes() == b"model"


def test_missing_printed_model_is_refused_before_building(tmp_path):
    template = {
        **TEMPLATE,
        "printed_parts": [{"name": "clip", "model": str(tmp_path / "none.SLDPRT")}],
    }
    with pytest.raises(SpecError, match="none.SLDPRT"):
        run(tmp_path, Fake(), template)
    assert not (tmp_path / "out").exists()
