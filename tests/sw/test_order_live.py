from pathlib import Path

import pytest

from swlamp.kfactor.table import KTable
from swlamp.order.pipeline import SolidWorksSteps, run_order
from swlamp.sw import builder

pytestmark = pytest.mark.sw
EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_two_orders_from_one_template_give_two_complete_folders(sw_worker, tmp_path):
    template = EXAMPLES / "box4-inox08.template.yaml"
    before = template.read_bytes()
    table = KTable(tmp_path / "k.json")
    steps = SolidWorksSteps(sw_worker)
    reports = [
        run_order(template, EXAMPLES / name, steps, table, tmp_path / "orders")
        for name in ("order-200.yaml", "order-300.yaml")
    ]
    for report, oid in zip(reports, ("o200", "o300"), strict=True):
        assert report.status == "ok", report.errors
        folder = Path(report.folder)
        names = {p.name for p in folder.iterdir()}
        for part in ("shade", "cap"):
            for ext in ("dxf", "SLDPRT", "3mf", "stl"):
                assert f"{part}__{oid}.{ext}" in names
        assert {"summary.json", "summary.md"} <= names
    assert reports[1].parts[0].measured_bbox[3] == pytest.approx(150, abs=0.05)
    assert template.read_bytes() == before
    titles = sw_worker.run(lambda sw: builder.open_titles(sw))
    assert not [t for t in titles if "__o200" in t or "__o300" in t]
