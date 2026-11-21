"""Attach to a running SolidWorks 2025 and wrap its COM objects with early binding.

Facts verified live on SolidWorks 2025 SP5 (revision 33.5):

* Type libraries: SldWorks {83A33D31-27C5-11CE-BFD4-00400513BB57} and swconst
  {4687F359-55D0-4CD3-B6CF-2EB42C11F989}. The registry lists them as version "21.0",
  which is hexadecimal: pass major version 33 to ``gencache.EnsureModule``.
* ``win32com.client.GetActiveObject`` returns a late-bound object; wrap the raw
  ``IDispatch`` with the generated class instead (see :func:`typed`).
* With early binding, pass plain ``None`` for "Nothing" interface arguments and plain
  ints for by-reference out-parameters (``SaveAs3(..., None, None, 0, 0)``).
* In a sheet-metal part the Flat-Pattern feature stays last in the tree, so the newest
  sketch is not ``FeatureByPositionReverse(0)``; find features by type instead.
"""

from __future__ import annotations

import contextlib
import sys
from dataclasses import dataclass, field
from typing import Any

SLDWORKS_LIBID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
SWCONST_LIBID = "{4687F359-55D0-4CD3-B6CF-2EB42C11F989}"
TYPELIB_MAJOR = 33  # registry "21.0" is hex
MK_E_UNAVAILABLE = -2147221021

# System toggles that otherwise pop dialogs during export, and the value used while we work.
QUIET_TOGGLES = {
    "swSTLShowInfoOnSave": False,
    "sw3MFShowInfoOnSave": False,
    "swSTLPreview": False,
    "swDXFDontShowMap": True,
}


class SolidWorksNotRunning(RuntimeError):
    pass


def ensure_typelibs() -> tuple[Any, Any]:
    """Generate (or load) the early-binding wrappers without writing to stdout.

    makepy prints progress on first use, which would corrupt an MCP stdio stream.
    """
    from win32com.client import gencache

    with contextlib.redirect_stdout(sys.stderr):
        sw_mod = gencache.EnsureModule(SLDWORKS_LIBID, 0, TYPELIB_MAJOR, 0)
        const_mod = gencache.EnsureModule(SWCONST_LIBID, 0, TYPELIB_MAJOR, 0)
    if sw_mod is None or const_mod is None:
        raise RuntimeError("Không tạo được wrapper cho type library của SolidWorks 2025.")
    return sw_mod, const_mod


@dataclass
class Sw:
    """Typed handle to the running SolidWorks application."""

    app: Any
    lib: Any
    const: Any
    _saved_toggles: dict[str, bool] = field(default_factory=dict)

    def typed(self, obj: Any, iface: str) -> Any:
        """Wrap a COM object returned by SolidWorks with the generated interface class."""
        if obj is None:
            return None
        import pythoncom

        cls = getattr(self.lib, iface)
        ole = obj._oleobj_ if hasattr(obj, "_oleobj_") else obj
        return cls(ole.QueryInterface(cls.CLSID, pythoncom.IID_IDispatch))

    def quiet(self) -> None:
        """Turn off export dialogs; remember the user's values for :meth:`restore`."""
        for name, value in QUIET_TOGGLES.items():
            key = getattr(self.const, name)
            self._saved_toggles.setdefault(name, bool(self.app.GetUserPreferenceToggle(key)))
            self.app.SetUserPreferenceToggle(key, value)

    def restore(self) -> None:
        for name, value in self._saved_toggles.items():
            self.app.SetUserPreferenceToggle(getattr(self.const, name), value)
        self._saved_toggles.clear()

    def revision(self) -> str:
        return str(self.app.RevisionNumber())


def attach() -> Sw:
    """Attach to the SolidWorks instance the user already has open. Never starts one."""
    import pythoncom
    import pywintypes

    lib, const_mod = ensure_typelibs()
    try:
        unknown = pythoncom.GetActiveObject("SldWorks.Application")
    except pywintypes.com_error as exc:
        if exc.hresult == MK_E_UNAVAILABLE:
            raise SolidWorksNotRunning(
                "SolidWorks chưa chạy. Mở SolidWorks 2025 rồi thử lại."
            ) from None
        raise
    app = lib.ISldWorks(unknown.QueryInterface(pythoncom.IID_IDispatch))
    if not app.StartupProcessCompleted:
        raise SolidWorksNotRunning(
            "SolidWorks đang khởi động, chờ cửa sổ chính hiện ra rồi thử lại."
        )
    return Sw(app=app, lib=lib, const=const_mod.constants)


def probe() -> str:
    """Cheap round-trip used to decide whether a stuck worker may restart."""
    return attach().revision()


def main_prepare() -> None:
    """Pre-generate the early-binding wrappers (``swlamp-mcp --prepare``)."""
    import pythoncom

    pythoncom.CoInitialize()
    ensure_typelibs()
    print("Đã tạo wrapper SolidWorks 2025.", file=sys.stderr)
