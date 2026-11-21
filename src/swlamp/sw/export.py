"""Exports from an open SolidWorks part: flat-pattern DXF (for checking), STL/3MF, images."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pythoncom
from PIL import Image
from win32com.client import VARIANT

from .connection import Sw

FLAT_GEOMETRY_AND_BENDS = 1 | 4  # swExportToDWG sheet-metal options: geometry + bend lines


class ExportError(RuntimeError):
    pass


def flat_dxf(sw: Sw, doc, path: Path) -> Path:
    """SolidWorks' own flat-pattern export, used only to cross-check the shop DXF."""
    model = sw.typed(doc, "IModelDoc2")
    part = sw.typed(doc, "IPartDoc")
    align = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [0.0] * 12)
    ok = part.ExportToDWG2(
        str(path), model.GetPathName(), 1, True, align, False, False, FLAT_GEOMETRY_AND_BENDS, None
    )
    if not ok or not path.exists():
        raise ExportError("SolidWorks không xuất được flat pattern ra DXF.")
    return path


def mesh(sw: Sw, doc, path: Path) -> Path:
    """Save a copy as STL or 3MF (chosen by the extension), in millimetres."""
    model = sw.typed(doc, "IModelDoc2")
    ext = sw.typed(model.Extension, "IModelDocExtension")
    options = sw.const.swSaveAsOptions_Silent | sw.const.swSaveAsOptions_Copy
    ok, err, _warn = ext.SaveAs3(str(path), 0, options, None, None, 0, 0)
    if not ok or not path.exists() or path.stat().st_size == 0:
        raise ExportError(f"Không xuất được {path.name} (mã lỗi {err}).")
    return path


def screenshot(sw: Sw, doc, path: Path, width: int = 900, height: int = 700) -> Path:
    """Isometric PNG of the part as SolidWorks shows it."""
    model = sw.typed(doc, "IModelDoc2")
    model.ShowNamedView2("*Isometric", 7)
    model.ViewZoomtofit2()
    fd, bmp = tempfile.mkstemp(suffix=".bmp")
    os.close(fd)
    try:
        if not model.SaveBMP(bmp, width, height):
            raise ExportError("SolidWorks không chụp được ảnh (cửa sổ có thể đang bị khoá).")
        with Image.open(bmp) as img:
            img.convert("RGB").save(path, "PNG")
    finally:
        Path(bmp).unlink(missing_ok=True)
    return path
