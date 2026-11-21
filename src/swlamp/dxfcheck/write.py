"""Write the shop DXF straight from the flat blank.

Layers: ``CUT`` (outline and every cut), ``BEND_UP`` and ``BEND_DOWN`` (bend centre
lines, named so most laser and press-brake CAM recognises them). Units mm
(``$INSUNITS`` = 4), DXF R2000, only LINE / CIRCLE / LWPOLYLINE entities, nominal
geometry with no kerf offset (the shop applies kerf).
"""

from __future__ import annotations

from pathlib import Path

import ezdxf

from ..geometry.blank import Blank
from ..geometry.shapes import Circle

CUT, BEND_UP, BEND_DOWN = "CUT", "BEND_UP", "BEND_DOWN"
LAYERS = {CUT: 7, BEND_UP: 1, BEND_DOWN: 5}  # ACI colours: white, red, blue


def write_dxf(blank: Blank, path: Path) -> Path:
    doc = ezdxf.new("R2000", setup=True)
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    for name, colour in LAYERS.items():
        layer = doc.layers.add(name, color=colour)
        if name != CUT:
            layer.dxf.linetype = "DASHED"
    msp = doc.modelspace()
    msp.add_lwpolyline(
        list(blank.outline.exterior.coords)[:-1], close=True, dxfattribs={"layer": CUT}
    )
    for cut in blank.cuts:
        if isinstance(cut, Circle):
            msp.add_circle((cut.cx, cut.cy), cut.r, dxfattribs={"layer": CUT})
        else:
            msp.add_lwpolyline(cut.points, close=True, dxfattribs={"layer": CUT})
    for b in blank.bends:
        msp.add_line(
            (b.x1, b.y1), (b.x2, b.y2), dxfattribs={"layer": BEND_UP if b.up else BEND_DOWN}
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)
    return path
