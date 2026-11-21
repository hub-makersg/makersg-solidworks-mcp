from collections import Counter

import ezdxf
import pytest

from swlamp.dxfcheck.compare import compare
from swlamp.dxfcheck.validate import validate
from swlamp.dxfcheck.write import write_dxf
from swlamp.geometry.blank import build_blank
from swlamp.kfactor.table import Lookup
from swlamp.spec.merge import resolve


@pytest.fixture
def blank():
    lamp = resolve(
        {
            "name": "t",
            "material": "stainless",
            "thickness": 0.8,
            "parts": [
                {
                    "name": "box",
                    "width": 200,
                    "depth": 200,
                    "walls": {s: {"height": 80} for s in ("front", "back", "left", "right")},
                    "holes": [{"d": 40}],
                    "patterns": [{"face": "left", "kind": "hex", "size": 8, "web": 2}],
                }
            ],
        }
    )
    return build_blank(lamp, lamp.parts[0], Lookup(0.42, 1.26, "calibrated"))


def test_shop_dxf_has_three_layers_mm_and_allowed_entities(blank, tmp_path):
    path = write_dxf(blank, tmp_path / "box.dxf")
    doc = ezdxf.readfile(path)
    assert doc.header["$INSUNITS"] == 4
    kinds = Counter((e.dxftype(), e.dxf.layer) for e in doc.modelspace())
    assert {layer for _, layer in kinds} == {"CUT", "BEND_UP"}
    assert {kind for kind, _ in kinds} <= {"LINE", "CIRCLE", "LWPOLYLINE"}
    assert kinds[("LINE", "BEND_UP")] == 4
    assert validate(path, blank) == []


def test_same_blank_writes_same_geometry(blank, tmp_path):
    def entities(p):
        return [
            (e.dxftype(), e.dxf.layer, str(e.get_points()) if e.dxftype() == "LWPOLYLINE" else "")
            for e in ezdxf.readfile(p).modelspace()
        ]

    assert entities(write_dxf(blank, tmp_path / "a.dxf")) == entities(
        write_dxf(blank, tmp_path / "b.dxf")
    )


def test_open_cut_contour_is_reported_with_location(blank, tmp_path):
    path = write_dxf(blank, tmp_path / "box.dxf")
    doc = ezdxf.readfile(path)
    doc.modelspace().add_lwpolyline(
        [(1, 2), (5, 2), (5, 6)], close=False, dxfattribs={"layer": "CUT"}
    )
    doc.saveas(path)
    assert any("hở" in p and "(1.00, 2.00)" in p for p in validate(path, blank))


def test_short_bend_line_is_reported(blank, tmp_path):
    path = write_dxf(blank, tmp_path / "box.dxf")
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    line = next(e for e in msp if e.dxf.layer == "BEND_UP")
    s, e = line.dxf.start, line.dxf.end
    line.dxf.end = (s.x + (e.x - s.x) / 2, s.y + (e.y - s.y) / 2, 0)
    doc.saveas(path)
    assert any("chỉ phủ" in p for p in validate(path, blank))


def test_compare_accepts_split_segments_and_rejects_moved_hole(blank, tmp_path):
    shop = write_dxf(blank, tmp_path / "shop.dxf")
    # A SolidWorks-like export: polylines exploded into lines, bend lines dashed on layer 0.
    sw = ezdxf.new("R2000", setup=True)
    msp = sw.modelspace()
    for e in ezdxf.readfile(shop).modelspace():
        if e.dxf.layer == "CUT" and e.dxftype() == "LWPOLYLINE":
            pts = [p[:2] for p in e.get_points()]
            for a, b in zip(pts, pts[1:] + pts[:1], strict=True):
                msp.add_line(a, b)
        elif e.dxftype() == "CIRCLE":
            msp.add_circle(e.dxf.center, e.dxf.radius)
        else:
            msp.add_line(e.dxf.start, e.dxf.end, dxfattribs={"linetype": "DASHED"})
    sw_path = tmp_path / "sw.dxf"
    sw.saveas(sw_path)
    assert compare(sw_path, shop) == []
    circle = next(e for e in msp if e.dxftype() == "CIRCLE")
    circle.dxf.center = (circle.dxf.center.x + 0.2, circle.dxf.center.y, 0)
    sw.saveas(sw_path)
    assert compare(sw_path, shop) and "0.2" in compare(sw_path, shop)[0]
