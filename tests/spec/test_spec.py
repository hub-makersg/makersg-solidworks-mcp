import copy
from pathlib import Path

import pytest

from swlamp.spec.merge import SpecError, load_yaml, resolve
from swlamp.spec.rules import check, min_flange

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
T, R, V = 0.8, 1.008, 4.8  # stainless 0.8 on an assumed 6T die


@pytest.fixture
def template():
    return load_yaml(EXAMPLES / "box4-inox08.template.yaml")


def test_example_template_loads_with_four_walls(template):
    lamp = resolve(template)
    shade = lamp.parts[0]
    assert set(shade.walls) == {"front", "back", "left", "right"}
    assert shade.walls["front"].height == 80
    assert lamp.parts[1].width == 220
    check(lamp, R, V)


@pytest.mark.parametrize("order_file", ["order-200.yaml", "order-300.yaml"])
def test_example_orders_pass_the_rules(template, order_file):
    check(resolve(template, load_yaml(EXAMPLES / order_file)), R, V)


def test_two_orders_give_two_sizes_and_leave_template_untouched(template):
    before = copy.deepcopy(template)
    a = resolve(template, {"order_id": "a", "params": {"width": 200}})
    b = resolve(template, {"order_id": "b", "params": {"width": 300}})
    assert a.parts[0].width == 200
    assert b.parts[0].width == 300
    assert b.parts[1].slots[2].x == pytest.approx(300 / 2 - 0.4)
    assert template == before


def test_order_text_parameter_reaches_engraving(template):
    lamp = resolve(template, {"order_id": "x", "params": {"label": 2024}})
    assert lamp.parts[0].texts[0].text == "2024"


def test_order_overriding_undeclared_parameter_names_it(template):
    with pytest.raises(SpecError, match="colour"):
        resolve(template, {"order_id": "x", "params": {"colour": "red"}})


def test_template_referencing_missing_parameter_says_where():
    tpl = {
        "name": "x",
        "material": "steel",
        "thickness": 1,
        "parts": [{"name": "p", "width": "{w}", "depth": 10}],
    }
    with pytest.raises(SpecError, match=r"parts\[0\]\.width.*w"):
        resolve(tpl)


def test_short_flange_on_stainless_08_is_rejected_with_minimum(template):
    tpl = copy.deepcopy(template)
    tpl["parts"][0]["walls"]["left"]["height"] = 2
    with pytest.raises(SpecError) as err:
        check(resolve(tpl), R, V)
    assert f"{min_flange(T, R, V):.2f}" in str(err.value)
    assert "shade.left" in str(err.value)


def test_hole_inside_bend_band_is_rejected(template):
    tpl = copy.deepcopy(template)
    tpl["parts"][0]["holes"].append({"face": "front", "x": 0, "y": 2, "d": 3})
    with pytest.raises(SpecError, match="dải cấm"):
        check(resolve(tpl), R, V)


def test_closed_hem_is_rejected_pointing_to_the_shop(template):
    tpl = copy.deepcopy(template)
    tpl["parts"][0]["walls"]["left"]["hem"] = {"length": 8, "kind": "closed"}
    with pytest.raises(SpecError, match="xưởng"):
        check(resolve(tpl), R, V)


def test_printed_part_may_only_change_ord_variables(template):
    tpl = copy.deepcopy(template)
    tpl["printed_parts"] = [{"name": "clip", "model": "clip.SLDPRT", "vars": {"Width": 20}}]
    with pytest.raises(SpecError, match="ord_"):
        resolve(tpl)
