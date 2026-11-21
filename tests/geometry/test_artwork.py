import math

import ezdxf
import pytest

from swlamp.geometry.artwork import ArtworkError, load


def test_svg_circle_is_flattened_within_tolerance(tmp_path):
    svg = tmp_path / "dot.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40">'
        '<circle cx="20" cy="20" r="10"/></svg>',
        encoding="utf-8",
    )
    (poly,) = load(svg, width=20, x=5, y=-3)
    cx, cy = poly.centroid.x, poly.centroid.y
    assert (cx, cy) == pytest.approx((5, -3), abs=1e-3)
    for x, y in poly.exterior.coords:
        assert 10 - 0.02 <= math.hypot(x - cx, y - cy) <= 10 + 1e-6
    assert poly.bounds[2] - poly.bounds[0] == pytest.approx(20, abs=0.02)


def test_dxf_rectangle_scales_to_width(tmp_path):
    doc = ezdxf.new()
    doc.modelspace().add_lwpolyline([(0, 0), (4, 0), (4, 2), (0, 2)], close=True)
    path = tmp_path / "r.dxf"
    doc.saveas(path)
    (poly,) = load(path, width=40)
    x0, y0, x1, y1 = poly.bounds
    assert (x1 - x0, y1 - y0) == pytest.approx((40, 20))
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == pytest.approx((0, 0))


def test_artwork_with_loose_island_is_rejected(tmp_path):
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True)
    msp.add_lwpolyline([(3, 3), (7, 3), (7, 7), (3, 7)], close=True)
    msp.add_lwpolyline([(4, 4), (6, 4), (6, 6), (4, 6)], close=True)
    path = tmp_path / "ring.dxf"
    doc.saveas(path)
    with pytest.raises(ArtworkError, match="đảo"):
        load(path, width=10)
