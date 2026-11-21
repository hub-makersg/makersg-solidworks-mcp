import asyncio
import math
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from swlamp.server import create_server

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def names(server):
    return {t.name for t in asyncio.run(server.list_tools())}


def call(server, name, args):
    return asyncio.run(server.call_tool(name, args))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SWLAMP_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("SWLAMP_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.delenv("SWLAMP_ENABLE_SCRIPT", raising=False)


def test_script_tool_is_absent_by_default():
    assert "run_script" not in names(create_server())
    assert {"run_order", "validate_spec", "preview_flat", "calibration_record"} <= names(
        create_server()
    )


def test_script_tool_appears_only_when_enabled(monkeypatch):
    monkeypatch.setenv("SWLAMP_ENABLE_SCRIPT", "1")
    assert "run_script" in names(create_server())


def test_validate_spec_reports_the_failing_field():
    bad = "name: x\nmaterial: steel\nthickness: 1\nparts:\n  - {name: p, width: -5, depth: 10}\n"
    with pytest.raises(ToolError, match=r"parts\.0\.width"):
        call(create_server(), "validate_spec", {"template": bad})


def test_preview_flat_works_without_solidworks():
    result = call(
        create_server(),
        "preview_flat",
        {
            "template": str(EXAMPLES / "box4-inox08.template.yaml"),
            "order": str(EXAMPLES / "order-300.yaml"),
        },
    )
    assert not result.is_error
    assert result.content[0].type == "image"


def test_validate_spec_gives_flat_size():
    result = call(
        create_server(), "validate_spec", {"template": str(EXAMPLES / "box4-inox08.template.yaml")}
    )
    assert not result.is_error
    data = result.structured_content
    shade = data["parts"][0]
    assert shade["part"] == "shade"
    assert data["k_status"] == "provisional"
    # Stainless 0.8 on an assumed 4.8 mm die: R = 1.008, provisional K = 0.42.
    t, r, k = 0.8, 0.21 * 4.8, 0.42
    c = (r + t) - math.pi / 4 * (r + k * t)
    width = 2 * (100 - c + 80 - c + (t + 2))  # walls 80 high, tabs T + 2 mm
    depth = 2 * (100 - c + 80 - 2 * c + 8 - c)  # front/back walls with an 8 mm lip
    assert shade["flat_mm"] == pytest.approx([width, depth], abs=0.01)


def test_calibration_record_updates_table():
    t, r, k_true, flat = 0.8, 0.21 * 4.8, 0.44, 77.9
    bd = 2 * (r + t) - math.pi / 2 * (r + k_true * t)
    leg = (flat + bd) / 2
    server = create_server()
    result = call(
        server,
        "calibration_record",
        {"material": "stainless", "thickness": t, "flat_length": flat, "a": [leg], "b": [leg]},
    )
    assert not result.is_error
    assert result.structured_content["k"] == pytest.approx(k_true, abs=1e-4)
    rows = call(server, "k_table", {}).structured_content["rows"]
    assert rows["default|stainless|0.8|auto"]["k"] == pytest.approx(k_true, abs=1e-4)
