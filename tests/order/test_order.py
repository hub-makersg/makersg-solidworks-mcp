import json
from pathlib import Path

import ezdxf
import pytest

from swlamp.dxfcheck.write import write_dxf
from swlamp.kfactor.table import CALIBRATED, Entry, Key, KTable
from swlamp.order.pipeline import PartOutcome, run_order
from swlamp.paths import Guard, PathEscape, new_order_dir

from .fakes import hits_for

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
TEMPLATE = EXAMPLES / "box4-inox08.template.yaml"


class FakeSolidWorks:
    """Stands in for SolidWorks: reports a folded size and writes the files it would."""

    def __init__(self, bbox_offset=0.0):
        self.offset = bbox_offset

    def produce(self, parts, printed):
        out = []
        for pj in parts:
            sw = ezdxf.new("R2000", setup=True)
            msp = sw.modelspace()
            for e in ezdxf.readfile(write_dxf(pj.blank, pj.sw_flat)).modelspace():
                if e.dxf.layer == "CUT":
                    msp.add_foreign_entity(e.copy())
                else:
                    msp.add_line(e.dxf.start, e.dxf.end, dxfattribs={"linetype": "DASHED"})
            sw.saveas(pj.sw_flat)
            for f in (pj.sldprt, *pj.meshes, pj.image):
                f.write_bytes(b"x")
            bbox = list(pj.blank.folded_bbox)
            bbox[3] += self.offset
            out.append(PartOutcome(tuple(bbox), hits=hits_for(pj.blank)))
        return out


@pytest.fixture
def table(tmp_path):
    return KTable(tmp_path / "k.json")


def test_order_writes_dxf_per_part_and_summary(tmp_path, table):
    report = run_order(TEMPLATE, EXAMPLES / "order-200.yaml", FakeSolidWorks(), table, tmp_path)
    folder = Path(report.folder)
    assert report.status == "ok", report.errors
    assert sorted(p.name for p in folder.glob("*.dxf")) == ["cap__o200.dxf", "shade__o200.dxf"]
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert summary["thickness"] == 0.8
    assert not (folder / "_check").exists()


def test_provisional_k_is_flagged_in_summary(tmp_path, table):
    report = run_order(TEMPLATE, EXAMPLES / "order-200.yaml", FakeSolidWorks(), table, tmp_path)
    text = (Path(report.folder) / "summary.md").read_text(encoding="utf-8")
    assert "K chưa hiệu chỉnh" in text


def test_calibrated_key_has_no_k_caveat(tmp_path, table):
    table.store(Key("stainless", 0.8), Entry(k=0.43, radius=1.0, status=CALIBRATED))
    report = run_order(TEMPLATE, EXAMPLES / "order-200.yaml", FakeSolidWorks(), table, tmp_path)
    assert report.uncalibrated() == []
    assert report.parts[0].k == pytest.approx(0.43)


def test_folded_size_off_by_03_fails_without_any_dxf(tmp_path, table):
    report = run_order(TEMPLATE, EXAMPLES / "order-200.yaml", FakeSolidWorks(0.3), table, tmp_path)
    assert report.status == "error"
    assert any("lệch" in e for e in report.errors)
    assert list(Path(report.folder).glob("*.dxf")) == []
    assert "LỖI" in (Path(report.folder) / "summary.md").read_text(encoding="utf-8")


def test_same_order_twice_keeps_first_folder(tmp_path, table):
    first = run_order(TEMPLATE, EXAMPLES / "order-200.yaml", FakeSolidWorks(), table, tmp_path)
    marker = Path(first.folder) / "summary.json"
    before = marker.read_bytes()
    second = run_order(TEMPLATE, EXAMPLES / "order-200.yaml", FakeSolidWorks(), table, tmp_path)
    assert Path(second.folder).name == "o200-2"
    assert marker.read_bytes() == before


def test_non_90_degree_bend_stays_uncalibrated(tmp_path, table):
    table.store(Key("stainless", 0.8), Entry(k=0.43, radius=1.0, status=CALIBRATED))
    tpl = {
        "name": "h",
        "material": "stainless",
        "thickness": 0.8,
        "parts": [
            {
                "name": "tray",
                "width": 120,
                "depth": 80,
                "walls": {"front": {"height": 30, "hem": {"length": 8}}},
            }
        ],
    }
    report = run_order(tpl, {"order_id": "h1"}, FakeSolidWorks(), table, tmp_path)
    assert report.uncalibrated() == ["tray: nếp hem 180°"]


def test_guard_blocks_paths_leaving_the_order_folder(tmp_path):
    folder = new_order_dir(tmp_path, "o1")
    guard = Guard(folder)
    assert guard.path("a.dxf").parent == folder.resolve()
    with pytest.raises(PathEscape):
        guard.path("../../x.dxf")
