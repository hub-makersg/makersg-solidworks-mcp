"""MCP server: lets Claude design flat-pack sheet-metal lamps in SolidWorks.

Run with ``uv run swlamp-mcp`` (stdio). ``swlamp-mcp --prepare`` pre-generates the
SolidWorks COM wrappers so the first tool call does not have to.
"""

from __future__ import annotations

import contextlib
import functools
import io
import sys
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import config
from .geometry.preview import render
from .kfactor.calibrate import COUPON_LEG, COUPON_WIDTH, calibrate
from .kfactor.table import Key, KTable
from .order.pipeline import SolidWorksSteps, plan, run_order
from .spec.merge import SpecError, load_yaml, parse_yaml
from .spec.models import Material, Order

INSTRUCTIONS = """\
Thiết kế đèn decor tôn (cắt laser + chấn) trên SolidWorks 2025 đang mở.
Quy trình: viết template YAML (xem docs/spec-format.md) → validate_spec → preview_flat →
run_order với thông số đơn. Kích thước tính bằng mm, là kích thước ngoài sau khi gập.
Trước khi gia công thật, hiệu chỉnh K: calibration_coupon → xưởng chấn → calibration_record.
"""

_worker = None


def _get_worker():
    global _worker
    if _worker is None:
        from .sw.connection import attach, probe
        from .sw.worker import StaWorker

        _worker = StaWorker(on_start=attach, probe=probe)
    return _worker


def _yaml(value: str | None) -> dict | None:
    """Accept a path to a YAML file or the YAML text itself."""
    if value is None or value == "":
        return None
    if "\n" not in value and Path(value).suffix.lower() in (".yaml", ".yml"):
        if not Path(value).exists():
            raise SpecError(f"Không thấy file {value}")
        return load_yaml(value)
    return parse_yaml(value)


def _prepare(template: str, order: str | None):
    order_data = _yaml(order)
    return plan(_yaml(template), Order.model_validate(order_data) if order_data else None, KTable())


def _out_dir(name: str) -> Path:
    out = config.output_root() / name
    out.mkdir(parents=True, exist_ok=True)
    return out


def _part_info(blank, lookup) -> dict[str, Any]:
    x0, y0, x1, y1 = blank.flat_bbox
    return {
        "part": blank.part,
        "flat_mm": [round(x1 - x0, 2), round(y1 - y0, 2)],
        "folded_bbox_mm": [round(v, 2) for v in blank.folded_bbox],
        "cuts": len(blank.cuts),
        "bends": [f"{b.kind} {b.angle:g}° ({lookup.status_for(b.angle)})" for b in blank.bends],
        "k": round(blank.k, 4),
        "radius_mm": round(blank.radius, 3),
    }


def _user_errors(fn):
    """Let the model see our error messages: the SDK hides text of non-ToolError exceptions."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(str(exc) or exc.__class__.__name__) from exc

    return wrapper


def create_server(enable_script: bool | None = None) -> MCPServer:
    mcp = MCPServer("swlamp", instructions=INSTRUCTIONS, version="0.1.0")

    @mcp.tool()
    @_user_errors
    def sw_status() -> str:
        """Kiểm tra SolidWorks 2025 đang mở và trả lời được."""
        rev = _get_worker().run(lambda sw: sw.revision(), timeout=30)
        return f"SolidWorks đang chạy, phiên bản {rev}."

    @mcp.tool()
    @_user_errors
    def validate_spec(template: str, order: str | None = None) -> dict[str, Any]:
        """Kiểm template (+ đơn) theo luật gia công và tính bản phẳng, không cần SolidWorks.

        template / order: đường dẫn file YAML hoặc nội dung YAML.
        """
        lamp, lookup, blanks = _prepare(template, order)
        return {
            "ok": True,
            "material": lamp.material,
            "thickness": lamp.thickness,
            "k_status": lookup.status,
            "parts": [_part_info(b, lookup) for b in blanks],
        }

    @mcp.tool()
    @_user_errors
    def preview_flat(template: str, order: str | None = None, part: str | None = None) -> Image:
        """Ảnh PNG bản phẳng dự đoán của một part (mặc định part đầu tiên), không cần SolidWorks."""
        _, _, blanks = _prepare(template, order)
        blank = next((b for b in blanks if part in (None, b.part)), None)
        if blank is None:
            raise SpecError(f"Không có part '{part}'.")
        out = _out_dir("_preview")
        return Image(path=render(blank, out / f"{blank.part}.flat.png", size=800))

    @mcp.tool(name="run_order")
    @_user_errors
    def run_order_tool(template: str, order: str | None = None) -> list[Any]:
        """Chạy một đơn: dựng mọi part trong SolidWorks, kiểm kích thước, xuất DXF/SLDPRT/3MF/STL.

        Trả tóm tắt đơn và ảnh isometric của part đầu tiên.
        """
        tpl = _yaml(template)
        report = run_order(tpl, _yaml(order), SolidWorksSteps(_get_worker()))
        md = (Path(report.folder) / "summary.md").read_text(encoding="utf-8")
        content: list[Any] = [f"Thư mục đơn: {report.folder}\n\n{md}"]
        pngs = [p for p in report.images if p.endswith(".png") and not p.endswith(".flat.png")]
        if pngs:
            content.append(Image(path=pngs[0]))
        return content

    @mcp.tool()
    @_user_errors
    def screenshot() -> Image:
        """Ảnh isometric của tài liệu đang mở trong SolidWorks."""
        from .sw import export

        out = _out_dir("_preview")
        path = out / "active.png"
        _get_worker().run(lambda sw: export.screenshot(sw, sw.app.ActiveDoc, path))
        return Image(path=path)

    @mcp.tool()
    @_user_errors
    def measure() -> dict[str, Any]:
        """Khung bao (mm) và lỗi rebuild của part đang mở trong SolidWorks."""
        from .sw import builder

        def job(sw):
            doc = sw.app.ActiveDoc
            if doc is None:
                raise RuntimeError("SolidWorks không có tài liệu nào đang mở.")
            bbox, bodies = builder.body_bbox(sw, doc)
            return {
                "bbox_mm": list(bbox),
                "bodies": bodies,
                "errors": builder.feature_errors(sw, doc),
            }

        return _get_worker().run(job)

    @mcp.tool()
    @_user_errors
    def k_table() -> dict[str, Any]:
        """Các dòng của bảng K đã lưu (khoá: xưởng|vật liệu|độ dày|cối V)."""
        table = KTable()
        return {"path": str(table.path), "rows": {k: vars(v) for k, v in table.rows().items()}}

    @mcp.tool()
    @_user_errors
    def calibration_coupon(
        material: Material, thickness: float, shop: str = "default", die_v: float | None = None
    ) -> dict[str, Any]:
        """Tạo thanh thử chữ L (rộng 100, hai cánh 40 mm) và xuất DXF để xưởng chấn.

        Trả chiều dài phẳng L; sau khi chấn, đo hai cạnh ngoài A, B rồi gọi calibration_record.
        """
        tag = f"{material[:2].upper()}{thickness:g}".replace(".", "")
        tpl = {
            "name": "coupon",
            "material": material,
            "thickness": thickness,
            "shop": shop,
            **({"die_v": die_v} if die_v else {}),
            "parts": [
                {
                    "name": "coupon",
                    "width": COUPON_WIDTH,
                    "depth": COUPON_LEG,
                    "walls": {"front": {"height": COUPON_LEG}},
                    "texts": [
                        {"face": "base", "text": tag, "height": max(8.0, 10 * thickness), "y": 8}
                    ],
                }
            ],
        }
        report = run_order(tpl, {"order_id": f"coupon-{tag}"}, SolidWorksSteps(_get_worker()))
        if report.status != "ok":
            return {
                "folder": report.folder,
                "status": report.status,
                "errors": report.errors,
                "next": "Thanh thử chưa tạo được; sửa các lỗi trên rồi gọi lại. "
                "Không gửi gì cho xưởng.",
            }
        flat = report.parts[0].flat_size[1]
        return {
            "folder": report.folder,
            "status": report.status,
            "errors": report.errors,
            "flat_length_L_mm": flat,
            "next": "Gửi DXF cho xưởng chấn 90°, đo hai cạnh ngoài A, B (thước cặp, 3 điểm), "
            "rồi gọi calibration_record với L này.",
        }

    @mcp.tool()
    @_user_errors
    def calibration_record(
        material: Material,
        thickness: float,
        flat_length: float,
        a: list[float],
        b: list[float],
        shop: str = "default",
        die_v: float | None = None,
    ) -> dict[str, Any]:
        """Tính K từ số đo thanh thử (A, B có thể nhiều mẫu) và lưu vào bảng K."""
        if len(a) != len(b):
            raise SpecError("Số mẫu A và B phải bằng nhau.")
        result = calibrate(
            KTable(),
            Key(material, thickness, shop, die_v),
            flat_length,
            list(zip(a, b, strict=True)),
        )
        return {
            "key": result.key.text(),
            "k": round(result.entry.k, 4),
            "radius_mm": round(result.entry.radius, 3),
            "spread": round(result.entry.spread, 4),
            "warning": result.warning,
        }

    @mcp.tool()
    @_user_errors
    def export_mesh(fmt: str = "3mf") -> str:
        """Xuất part đang mở trong SolidWorks ra 3MF hoặc STL (mm) vào thư mục _exports."""
        from .sw import export

        fmt = fmt.lower()
        if fmt not in ("3mf", "stl"):
            raise SpecError("fmt phải là '3mf' hoặc 'stl'.")
        out = _out_dir("_exports")

        def job(sw):
            doc = sw.typed(sw.app.ActiveDoc, "IModelDoc2")
            sw.quiet()
            try:
                return export.mesh(sw, doc, out / f"{Path(doc.GetTitle()).stem}.{fmt}")
            finally:
                sw.restore()

        return str(_get_worker().run(job))

    if config.script_tool_enabled() if enable_script is None else enable_script:

        @mcp.tool()
        @_user_errors
        def run_script(code: str) -> str:
            """Chạy Python tuỳ ý với biến `sw` (SolidWorks). Chỉ bật khi SWLAMP_ENABLE_SCRIPT=1."""

            def job(sw):
                buf = io.StringIO()
                scope = {"sw": sw}
                with contextlib.redirect_stdout(buf):
                    exec(code, scope)  # noqa: S102 - opt-in escape hatch
                return buf.getvalue() + (
                    f"\nresult = {scope['result']!r}" if "result" in scope else ""
                )

            return _get_worker().run(job)

    return mcp


def main() -> None:
    if "--prepare" in sys.argv[1:]:
        from .sw.connection import main_prepare

        main_prepare()
        return
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
