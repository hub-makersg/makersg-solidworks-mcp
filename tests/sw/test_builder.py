import dataclasses

import pytest
from shapely.geometry import box as rect
from shapely.ops import unary_union

from swlamp.geometry.blank import build_blank
from swlamp.kfactor.table import Lookup
from swlamp.spec.merge import resolve
from swlamp.sw import builder

pytestmark = pytest.mark.sw
LOOKUP = Lookup(0.42, 1.26, "calibrated")


def make_blank(walls, **part):
    lamp = resolve(
        {
            "name": "t",
            "material": "stainless",
            "thickness": 0.8,
            "parts": [{"name": "b", "width": 200, "depth": 160, "walls": walls, **part}],
        }
    )
    return build_blank(lamp, lamp.parts[0], LOOKUP)


def run_build(sw_worker, blank, path):
    def job(sw):
        result = builder.build(sw, blank, path)
        builder.close(sw, result.title)
        return result

    return sw_worker.run(job)


def test_four_wall_box_matches_outside_dimensions(sw_worker, tmp_path):
    blank = make_blank({s: {"height": 80} for s in ("front", "back", "left", "right")})
    result = run_build(sw_worker, blank, tmp_path / "box4__t1.SLDPRT")
    assert result.errors == []
    assert result.bodies == 1
    for got, want in zip(result.bbox, blank.folded_bbox, strict=True):
        assert got == pytest.approx(want, abs=0.05)


def test_chained_lip_and_open_hem_build_without_errors(sw_worker, tmp_path):
    walls = {
        "front": {"height": 60, "lip": 10},
        "back": {"height": 60, "hem": {"length": 8}},
        "left": {"height": 60},
        "right": {"height": 60},
    }
    blank = make_blank(walls, holes=[{"x": 0, "y": 0, "d": 30}])
    result = run_build(sw_worker, blank, tmp_path / "lip__t2.SLDPRT")
    assert result.errors == []
    assert result.bbox[3] == pytest.approx(100, abs=0.05)
    assert result.bbox[5] == pytest.approx(60 - 0.8, abs=0.05)


def test_missing_corner_relief_is_reported_not_hung(sw_worker, tmp_path):
    blank = make_blank({s: {"height": 40} for s in ("front", "back", "left", "right")})
    corners = {(b.x1, b.y1) for b in blank.bends} | {(b.x2, b.y2) for b in blank.bends}
    # Fill the square corner reliefs back in: walls stay joined at the corners.
    filled = blank.outline.union(
        unary_union([rect(x - 3, y - 3, x + 3, y + 3) for x, y in corners])
    )
    broken = dataclasses.replace(blank, outline=filled)
    result = run_build(sw_worker, broken, tmp_path / "norelief__t3.SLDPRT")
    assert result.errors
