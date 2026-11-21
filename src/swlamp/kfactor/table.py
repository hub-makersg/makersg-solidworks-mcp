"""K-factor table keyed by (shop, material, thickness, die opening).

Each row stores the K-factor together with the inside radius R it was fitted with: a K
back-solved from a test coupon only reproduces the measured bend when the same R is used.
Rows fitted from a 90° coupon are trusted for 90° bends only.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from ..config import config_dir

# Air bending: inside radius ≈ p × die opening (TheFabricator "20 % rule").
RADIUS_FACTOR = {"stainless": 0.21, "steel": 0.16, "aluminium": 0.12}
DIE_PER_THICKNESS = 6.0  # typical V-die for thin sheet when the shop's die is unknown

CALIBRATED = "calibrated"
PROVISIONAL = "provisional"


@dataclass(frozen=True)
class Key:
    material: str
    thickness: float
    shop: str = "default"
    die_v: float | None = None

    @property
    def die(self) -> float:
        return self.die_v if self.die_v else DIE_PER_THICKNESS * self.thickness

    def text(self) -> str:
        v = f"{self.die_v:g}" if self.die_v else "auto"
        return f"{self.shop}|{self.material}|{self.thickness:g}|{v}"


@dataclass
class Entry:
    k: float
    radius: float
    status: str
    bd_measured: float | None = None
    samples: int = 0
    spread: float = 0.0
    date: str = field(default_factory=lambda: date.today().isoformat())


@dataclass(frozen=True)
class Lookup:
    k: float
    radius: float
    status: str

    def status_for(self, angle_deg: float) -> str:
        """A calibration only covers 90° bends; every other angle stays provisional."""
        return self.status if math.isclose(angle_deg, 90.0, abs_tol=0.01) else PROVISIONAL


def assumed_radius(key: Key) -> float:
    return RADIUS_FACTOR[key.material] * key.die


def provisional_k(radius: float, thickness: float) -> float:
    ratio = radius / thickness
    if ratio < 1:
        return 0.38
    if ratio <= 3:
        return 0.42
    return 0.50


class KTableError(RuntimeError):
    pass


class KTable:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_dir() / "ktable.json"

    def _read(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise KTableError(
                f"Bảng K bị hỏng ({self.path}): {exc}. Sửa hoặc xoá file rồi hiệu chỉnh lại."
            ) from None
        if not isinstance(data, dict):
            raise KTableError(f"Bảng K bị hỏng ({self.path}): không phải một mapping.")
        return data

    def rows(self) -> dict[str, Entry]:
        return {k: Entry(**v) for k, v in self._read().items()}

    def lookup(self, key: Key) -> Lookup:
        row = self._read().get(key.text())
        if row:
            e = Entry(**row)
            return Lookup(e.k, e.radius, e.status)
        radius = assumed_radius(key)
        return Lookup(provisional_k(radius, key.thickness), radius, PROVISIONAL)

    def store(self, key: Key, entry: Entry) -> None:
        data = self._read()
        data[key.text()] = asdict(entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".ktable-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
