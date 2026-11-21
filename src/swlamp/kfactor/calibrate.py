"""Back-solve the K-factor from an L-shaped test coupon.

The coupon is a strip with one 90° bend. After the shop bends it, the user measures the
two outside legs A and B. With L the designed flat length of the coupon:

    BD = A + B − L                      (measured bend deduction)
    BA = 2·(R + T) − BD                 (bend allowance, 90°: outside setback = R + T)
    K  = (BA / (π/2) − R) / T
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from ..geometry.bends import BendMath
from .table import CALIBRATED, Entry, Key, KTable, assumed_radius

COUPON_WIDTH = 100.0
COUPON_LEG = 40.0
PLAUSIBLE_K = (0.25, 0.55)


class CalibrationError(ValueError):
    pass


@dataclass(frozen=True)
class Calibration:
    key: Key
    entry: Entry
    warning: str | None


def back_solve(flat_length: float, a: float, b: float, thickness: float, radius: float) -> float:
    bd = a + b - flat_length
    if bd <= 0:
        raise CalibrationError(
            f"Số đo vô lý: A + B ({a + b:g}) phải lớn hơn chiều dài phẳng L ({flat_length:g})."
        )
    ba = 2 * (radius + thickness) - bd
    return (ba / (math.pi / 2) - radius) / thickness


def coupon_flat_length(key: Key, k: float, radius: float) -> float:
    """Flat length of a coupon whose legs measure COUPON_LEG outside when bent with (k, radius)."""
    return 2 * COUPON_LEG - 2 * BendMath(key.thickness, radius, k).inset(90)


def calibrate(
    table: KTable,
    key: Key,
    flat_length: float,
    samples: list[tuple[float, float]],
    radius: float | None = None,
) -> Calibration:
    """Fit K from one or more measured coupons and store it for ``key``."""
    if not samples:
        raise CalibrationError("Cần ít nhất một cặp số đo (A, B).")
    r = assumed_radius(key) if radius is None else radius
    ks = [back_solve(flat_length, a, b, key.thickness, r) for a, b in samples]
    k = statistics.fmean(ks)
    bds = [a + b - flat_length for a, b in samples]
    warning = None
    if not PLAUSIBLE_K[0] <= k <= PLAUSIBLE_K[1]:
        warning = (
            f"K = {k:.3f} nằm ngoài khoảng thường gặp {PLAUSIBLE_K[0]}–{PLAUSIBLE_K[1]}: "
            f"bán kính trong giả định R = {r:.2f} mm (cối V = {key.die:g} mm) có thể sai. "
            "Hãy hỏi xưởng độ mở cối V thật và hiệu chỉnh lại với V đó."
        )
    entry = Entry(
        k=k,
        radius=r,
        status=CALIBRATED,
        bd_measured=statistics.fmean(bds),
        samples=len(samples),
        spread=(max(ks) - min(ks)) if len(ks) > 1 else 0.0,
    )
    table.store(key, entry)
    return Calibration(key, entry, warning)
