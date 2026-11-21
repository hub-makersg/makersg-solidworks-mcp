import pytest

from swlamp.geometry.blank import build_blank
from swlamp.kfactor.table import Lookup
from swlamp.spec.merge import resolve


def test_tab_on_lower_wall_does_not_raise_predicted_top_above_taller_wall():
    lamp = resolve(
        {
            "name": "t",
            "material": "steel",
            "thickness": 1.0,
            "parts": [
                {
                    "name": "p",
                    "width": 160,
                    "depth": 120,
                    "walls": {"front": {"height": 80}, "back": {"height": 40}},
                    "tabs": [{"wall": "back", "at": [0], "width": 8, "length": 5}],
                }
            ],
        }
    )
    blank = build_blank(lamp, lamp.parts[0], Lookup(0.42, 1.0, "calibrated"))
    assert blank.folded_bbox[5] == pytest.approx(80 - 1.0)
