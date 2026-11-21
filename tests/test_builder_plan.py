from swlamp.geometry.blank import build_blank
from swlamp.kfactor.table import Lookup
from swlamp.spec.merge import resolve
from swlamp.sw.builder import plan_ops


def box(walls):
    lamp = resolve(
        {
            "name": "t",
            "material": "stainless",
            "thickness": 0.8,
            "parts": [{"name": "b", "width": 200, "depth": 200, "walls": walls}],
        }
    )
    return build_blank(lamp, lamp.parts[0], Lookup(0.42, 1.26, "calibrated"))


def test_four_wall_box_is_one_base_flange_then_four_bends():
    ops = plan_ops(box({s: {"height": 80} for s in ("front", "back", "left", "right")}))
    assert [o.kind for o in ops] == ["base_flange", "bend", "bend", "bend", "bend"]
    assert plan_ops(box({s: {"height": 80} for s in ("front", "back", "left", "right")})) == ops


def test_lips_and_hems_fold_before_walls():
    walls = {
        "front": {"height": 80, "lip": 8},
        "back": {"height": 80, "hem": {"length": 10}},
        "left": {"height": 80},
    }
    kinds = [o.detail[0] for o in plan_ops(box(walls)) if o.kind == "bend"]
    assert kinds.index("wall") > max(kinds.index("lip"), kinds.index("hem"))
    assert kinds.count("wall") == 3
