"""PNG drawing of a flat blank, available without SolidWorks."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .blank import Blank
from .shapes import Circle


def render(blank: Blank, path: Path, size: int = 900) -> Path:
    x0, y0, x1, y1 = blank.flat_bbox
    pad = 20
    scale = (size - 2 * pad) / max(x1 - x0, y1 - y0)
    w = int((x1 - x0) * scale) + 2 * pad
    h = int((y1 - y0) * scale) + 2 * pad

    def px(x: float, y: float) -> tuple[float, float]:
        return (pad + (x - x0) * scale, h - pad - (y - y0) * scale)

    img = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)
    draw.polygon(
        [px(x, y) for x, y in blank.outline.exterior.coords], fill=(220, 225, 232), outline="black"
    )
    for cut in blank.cuts:
        if isinstance(cut, Circle):
            a, b = px(cut.cx - cut.r, cut.cy + cut.r), px(cut.cx + cut.r, cut.cy - cut.r)
            draw.ellipse([a, b], fill="white", outline="black")
        else:
            draw.polygon([px(x, y) for x, y in cut.points], fill="white", outline="black")
    for bend in blank.bends:
        draw.line([px(bend.x1, bend.y1), px(bend.x2, bend.y2)], fill=(200, 30, 30), width=2)
    img.save(path, "PNG")
    return path
