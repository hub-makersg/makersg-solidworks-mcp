import math

import pytest

from swlamp.kfactor.calibrate import (
    CalibrationError,
    back_solve,
    calibrate,
    coupon_flat_length,
)
from swlamp.kfactor.table import CALIBRATED, Key, KTable


def legs_for(k_true, flat_length, t, r):
    """Forward model: what the shop would measure if the true K were k_true."""
    ba = math.pi / 2 * (r + k_true * t)
    bd = 2 * (r + t) - ba
    total = flat_length + bd
    return total / 2, total / 2


@pytest.fixture
def table(tmp_path):
    return KTable(tmp_path / "ktable.json")


def test_back_solve_recovers_true_k():
    t, r, L = 0.8, 1.26, 77.9
    a, b = legs_for(0.40, L, t, r)
    assert back_solve(L, a, b, t, r) == pytest.approx(0.40, abs=1e-9)


def test_calibration_stores_k_for_stainless_08(table):
    key = Key("stainless", 0.8)
    L = 77.9
    a, b = legs_for(0.44, L, 0.8, 1.008)
    result = calibrate(table, key, L, [(a, b)], radius=1.008)
    assert result.entry.k == pytest.approx(0.44, abs=1e-6)
    assert result.warning is None
    looked = table.lookup(key)
    assert looked.status == CALIBRATED
    assert looked.k == pytest.approx(0.44, abs=1e-6)
    assert looked.radius == pytest.approx(1.008)


def test_three_samples_average_and_report_spread(table):
    key = Key("steel", 1.0)
    L, r = 77.0, 0.96
    samples = [legs_for(k, L, 1.0, r) for k in (0.40, 0.42, 0.44)]
    result = calibrate(table, key, L, samples, radius=r)
    assert result.entry.k == pytest.approx(0.42, abs=1e-6)
    assert result.entry.spread == pytest.approx(0.04, abs=1e-6)
    assert result.entry.samples == 3


def test_negative_bend_deduction_is_rejected(table):
    with pytest.raises(CalibrationError, match="Số đo vô lý"):
        calibrate(table, Key("steel", 1.0), 80.0, [(39.0, 39.0)])


def test_implausible_k_is_stored_with_a_die_warning(table):
    key = Key("stainless", 0.8)
    L, r = 77.9, 1.0
    a, b = legs_for(0.19, L, 0.8, r)
    result = calibrate(table, key, L, [(a, b)], radius=r)
    assert result.entry.k == pytest.approx(0.19, abs=1e-6)
    assert "cối V" in result.warning


def test_coupon_flat_length_matches_bend_allowance():
    key = Key("stainless", 0.8)
    k, r = 0.42, 1.26
    ba = math.pi / 2 * (r + k * 0.8)
    expected = 2 * 40 - (2 * (r + 0.8) - ba)
    assert coupon_flat_length(key, k, r) == pytest.approx(expected)
    assert back_solve(expected, 40, 40, 0.8, r) == pytest.approx(k)
