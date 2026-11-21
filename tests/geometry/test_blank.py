import math

import pytest
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from swlamp.geometry.blank import GeometryError, build_blank
from swlamp.geometry.shapes import Circle
from swlamp.kfactor.table import Lookup
from swlamp.spec.merge import resolve

T, R, K = 0.8, 1.26, 0.42
LOOKUP = Lookup(K, R, "calibrated")


def lamp_with(part: dict, **extra):
    return resolve({"name": "t", "material": "stainless", "thickness": T, "parts": [part], **extra})


def inset90():
    """Standard flat-pattern geometry, independent of the code under test."""
    ba = math.pi / 2 * (R + K * T)
    return (R + T) - ba / 2


def box_part(**kw):
    part = {
        "name": "box",
        "width": 200,
        "depth": 200,
        "walls": {s: {"height": 80} for s in ("front", "back", "left", "right")},
    }
    part.update(kw)
    return part


def test_flat_size_follows_bend_allowance():
    lamp = lamp_with(box_part())
    blank = build_blank(lamp, lamp.parts[0], LOOKUP)
    c = inset90()
    half = 100 - c + (80 - c)
    x0, y0, x1, y1 = blank.flat_bbox
    assert x1 == pytest.approx(half, abs=1e-6)
    assert y1 == pytest.approx(half, abs=1e-6)
    assert x0 == pytest.approx(-half, abs=1e-6)
    walls = [b for b in blank.bends if b.kind == "wall"]
    assert len(walls) == 4
    assert {round(abs(b.y1), 6) for b in walls if b.y1 == b.y2} == {round(100 - c, 6)}


def test_same_spec_builds_identical_geometry():
    part = box_part(
        patterns=[{"face": "left", "kind": "hex", "size": 8, "web": 2}],
        texts=[{"face": "front", "text": "AN", "height": 20, "y": 40}],
    )
    lamp = lamp_with(part)
    a = build_blank(lamp, lamp.parts[0], LOOKUP)
    b = build_blank(lamp, lamp.parts[0], LOOKUP)
    assert list(a.outline.exterior.coords) == list(b.outline.exterior.coords)
    assert a.cuts == b.cuts
    assert a.bends == b.bends


def test_lettering_door_keeps_every_counter_attached():
    part = box_part(texts=[{"face": "front", "text": "DOOR", "height": 24, "y": 40}])
    lamp = lamp_with(part)
    blank = build_blank(lamp, lamp.parts[0], LOOKUP)
    letters = [Polygon(c.points) for c in blank.cuts if not isinstance(c, Circle)]
    assert letters
    material = blank.outline.difference(unary_union(letters))
    assert isinstance(material, Polygon), "a counter fell out as a separate piece"


def test_thin_lettering_is_rejected_with_minimum_size():
    part = box_part(texts=[{"face": "front", "text": "DOOR", "height": 3, "y": 40}])
    lamp = lamp_with(part)
    with pytest.raises(GeometryError, match="cỡ chữ tối thiểu"):
        build_blank(lamp, lamp.parts[0], LOOKUP)


def test_hex_pattern_keeps_clear_of_every_bend():
    part = box_part(
        patterns=[
            {"face": "base", "kind": "hex", "size": 8, "web": 2, "margin": 0},
            {"face": "left", "kind": "hex", "size": 8, "web": 2, "margin": 0},
        ]
    )
    lamp = lamp_with(part)
    blank = build_blank(lamp, lamp.parts[0], LOOKUP)
    ba = math.pi / 2 * (R + K * T)
    clear = 2 * T + R + ba / 2
    shapes = [c.shape() for c in blank.cuts]
    assert len(shapes) > 50
    for bend in blank.bends:
        line = LineString([(bend.x1, bend.y1), (bend.x2, bend.y2)])
        assert min(s.distance(line) for s in shapes) >= clear - 1e-6


def test_slot_clearance_includes_powder_coat():
    part = {
        "name": "cap",
        "width": 100,
        "depth": 100,
        "slots": [{"x": 0, "y": 0, "tab_width": 8, "angle": 0}],
    }
    lamp = lamp_with(part, coat_um=80)
    blank = build_blank(lamp, lamp.parts[0], LOOKUP)
    x0, y0, x1, y1 = blank.cuts[0].shape().bounds
    assert x1 - x0 == pytest.approx(8 + 0.25 + 0.32)
    assert y1 - y0 == pytest.approx(T + 0.25 + 0.32)


def test_open_hem_adds_its_developed_length_and_a_180_bend():
    part = box_part()
    part["walls"]["front"] = {"height": 80, "hem": {"length": 10}}
    lamp = lamp_with(part)
    blank = build_blank(lamp, lamp.parts[0], LOOKUP)
    c = inset90()
    ba180 = math.pi * (R + K * T)
    hem_inset = (R + T) - ba180 / 2
    expected = -(100 - c) - (80 - c - hem_inset) - (10 - hem_inset)
    assert blank.flat_bbox[1] == pytest.approx(expected, abs=1e-6)
    hems = [b for b in blank.bends if b.kind == "hem"]
    assert len(hems) == 1 and hems[0].angle == 180
    assert hems[0].y1 == pytest.approx(-(100 - c) - (80 - c - hem_inset), abs=1e-6)
    assert blank.bends[0].kind == "hem", "outermost bends fold first"


def test_cut_too_close_to_edge_is_rejected():
    part = {"name": "p", "width": 50, "depth": 50, "holes": [{"x": 24, "y": 0, "d": 2}]}
    lamp = lamp_with(part)
    with pytest.raises(GeometryError, match="cách mép"):
        build_blank(lamp, lamp.parts[0], LOOKUP)


def test_fixed_point_is_on_solid_base():
    part = box_part(holes=[{"x": 0, "y": 0, "d": 60}])
    lamp = lamp_with(part)
    blank = build_blank(lamp, lamp.parts[0], LOOKUP)
    pt = Point(blank.fixed_point)
    assert blank.outline.contains(pt)
    assert all(not c.shape().buffer(0.5).contains(pt) for c in blank.cuts)
