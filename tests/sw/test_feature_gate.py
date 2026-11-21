import dataclasses

import pytest

from swlamp.geometry.blank import build_blank
from swlamp.kfactor.table import Lookup
from swlamp.order.pipeline import _missing_features
from swlamp.spec.merge import resolve
from swlamp.sw import builder

pytestmark = pytest.mark.sw

PART = {
    "name": "gate",
    "width": 200,
    "depth": 160,
    "walls": {
        "front": {"height": 60, "lip": 10},
        "back": {"height": 60, "hem": {"length": 8}},
        "left": {"height": 40},
        "right": {"height": 60},
    },
    "patterns": [{"face": "right", "kind": "hex", "size": 8, "web": 2}],
    "tabs": [
        {"wall": "left", "at": [-30, 30], "width": 8},
        {"wall": "right", "at": [0], "width": 8},
    ],
}


def build_with_k(sw_worker, tmp_path, k):
    lamp = resolve({"name": "t", "material": "stainless", "thickness": 0.8, "parts": [PART]})
    predicted = build_blank(lamp, lamp.parts[0], Lookup(0.42, 1.26, "calibrated"))
    folded_with = dataclasses.replace(predicted, k=k)

    def job(sw):
        r = builder.build(sw, folded_with, tmp_path / f"gate__k{int(k * 100)}.SLDPRT")
        builder.close(sw, r.title)
        return r

    return predicted, sw_worker.run(job)


def test_every_feature_dimension_is_found_on_a_correct_build(sw_worker, tmp_path):
    predicted, result = build_with_k(sw_worker, tmp_path, 0.42)
    assert result.errors == []
    assert len(predicted.checks) == 7
    assert _missing_features(result.hits, predicted) == []


def test_wrong_k_factor_is_caught_feature_by_feature(sw_worker, tmp_path):
    predicted, result = build_with_k(sw_worker, tmp_path, 0.30)
    missing = _missing_features(result.hits, predicted)
    assert any("đầu hem" in m for m in missing)
    assert any("left: đỉnh tab" in m for m in missing)
