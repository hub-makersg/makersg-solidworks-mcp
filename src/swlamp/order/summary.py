"""Order summary written next to the files: what was made, with which K, and any caveats."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..kfactor.table import CALIBRATED


@dataclass
class BendReport:
    kind: str
    angle: float
    status: str


@dataclass
class PartReport:
    name: str
    k: float
    radius: float
    bends: list[BendReport]
    flat_size: tuple[float, float]
    folded_bbox: tuple[float, ...]
    files: list[str] = field(default_factory=list)
    measured_bbox: tuple[float, ...] = ()


@dataclass
class OrderReport:
    order_id: str
    folder: str
    material: str
    thickness: float
    status: str = "ok"  # "ok" or "error"
    parts: list[PartReport] = field(default_factory=list)
    printed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)

    def uncalibrated(self) -> list[str]:
        return [
            f"{p.name}: nếp {b.kind} {b.angle:g}°"
            for p in self.parts
            for b in p.bends
            if b.status != CALIBRATED
        ]


def write(report: OrderReport, folder: Path) -> None:
    (folder / "summary.json").write_text(
        json.dumps(asdict(report), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (folder / "summary.md").write_text(markdown(report), encoding="utf-8")


def markdown(r: OrderReport) -> str:
    lines = [f"# Đơn {r.order_id}", ""]
    lines.append(f"- Trạng thái: {'xong' if r.status == 'ok' else 'LỖI'}")
    lines.append(f"- Vật liệu: {r.material}, dày {r.thickness:g} mm")
    if r.errors:
        lines += ["", "## Lỗi", *[f"- {e}" for e in r.errors]]
    for p in r.parts:
        w, h = p.flat_size
        lines += [
            "",
            f"## {p.name}",
            f"- K = {p.k:.3f}, bán kính trong R = {p.radius:.2f} mm",
            f"- Bản phẳng: {w:.2f} × {h:.2f} mm",
            "- Khung bao dạng gập (mm): " + ", ".join(f"{v:.2f}" for v in p.folded_bbox),
        ]
        for b in p.bends:
            note = "" if b.status == CALIBRATED else " — K chưa hiệu chỉnh"
            lines.append(f"- Nếp {b.kind} {b.angle:g}°{note}")
        lines += [f"- File: {f}" for f in p.files]
    if r.printed:
        lines += ["", "## Chi tiết in", *[f"- {f}" for f in r.printed]]
    caveats = list(r.warnings)
    if r.uncalibrated():
        caveats.append(
            "K chưa hiệu chỉnh cho: "
            + "; ".join(r.uncalibrated())
            + ". Kích thước sau chấn có thể lệch quá ±0.5 mm."
        )
    if caveats:
        lines += ["", "## Lưu ý", *[f"- {c}" for c in caveats]]
    return "\n".join(lines) + "\n"
