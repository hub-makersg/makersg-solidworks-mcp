import pytest
from PIL import Image

from swlamp.dxfcheck.compare import compare
from swlamp.dxfcheck.validate import validate
from swlamp.dxfcheck.write import write_dxf
from swlamp.geometry.blank import build_blank
from swlamp.kfactor.table import Lookup
from swlamp.spec.merge import resolve
from swlamp.sw import builder, export

pytestmark = pytest.mark.sw


def test_box_exports_match_shop_dxf_and_mesh_files(sw_worker, tmp_path):
    lamp = resolve(
        {
            "name": "t",
            "material": "stainless",
            "thickness": 0.8,
            "parts": [
                {
                    "name": "box",
                    "width": 160,
                    "depth": 120,
                    "walls": {s: {"height": 50} for s in ("front", "back", "left", "right")},
                    "holes": [{"x": 20, "y": 10, "d": 30}],
                    "patterns": [{"face": "left", "kind": "hex", "size": 8, "web": 2}],
                    "texts": [{"face": "front", "text": "AB", "height": 18, "y": 25}],
                }
            ],
        }
    )
    blank = build_blank(lamp, lamp.parts[0], Lookup(0.42, 1.26, "calibrated"))
    shop = write_dxf(blank, tmp_path / "box__e1.dxf")

    def job(sw):
        sw.quiet()
        try:
            r = builder.build(sw, blank, tmp_path / "box__e1.SLDPRT")
            try:
                export.flat_dxf(sw, r.doc, tmp_path / "sw_flat.dxf")
                export.mesh(sw, r.doc, tmp_path / "box__e1.3mf")
                export.mesh(sw, r.doc, tmp_path / "box__e1.stl")
                export.screenshot(sw, r.doc, tmp_path / "box__e1.png")
            finally:
                builder.close(sw, r.title)
            return r
        finally:
            sw.restore()

    result = sw_worker.run(job)
    assert result.errors == []
    assert validate(shop, blank) == []
    assert compare(tmp_path / "sw_flat.dxf", shop) == []
    for name in ("box__e1.3mf", "box__e1.stl"):
        assert (tmp_path / name).stat().st_size > 1000
    with Image.open(tmp_path / "box__e1.png") as img:
        assert img.size == (900, 700)
