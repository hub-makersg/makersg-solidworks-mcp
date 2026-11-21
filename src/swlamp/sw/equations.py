"""Per-order copies of the user's parametric printed parts.

The user's model is copied into the order folder under an order-unique name and only the
copy is opened. Only global variables whose names start with ``ord_`` may change, and a
model whose equations live in a linked external file is refused, because writing them
would change the user's shared file.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .builder import BuildError, feature_errors, open_titles
from .connection import Sw

_LHS = re.compile(r'^\s*"([^"]+)"\s*=')
PREFIX = "ord_"


class EquationError(RuntimeError):
    pass


def check_names(values: dict[str, float]) -> None:
    bad = [k for k in values if not k.startswith(PREFIX)]
    if bad:
        raise EquationError(f"Chỉ được đổi biến có tiền tố '{PREFIX}': {', '.join(bad)}")


def global_variables(sw: Sw, doc) -> dict[str, int]:
    eqm = sw.typed(sw.typed(doc, "IModelDoc2").GetEquationMgr(), "IEquationMgr")
    found = {}
    for i in range(eqm.GetCount()):
        if eqm.GlobalVariable(i):
            m = _LHS.match(eqm.Equation(i))
            if m:
                found[m.group(1)] = i
    return found


def open_copy(sw: Sw, source: Path, dest: Path):
    """Copy ``source`` to ``dest`` and open the copy, never the original."""
    if any(t.lower().startswith(dest.stem.lower()) for t in open_titles(sw)):
        raise BuildError(f"SolidWorks đang mở một tài liệu tên '{dest.stem}'; đóng nó rồi thử lại.")
    if not source.exists():
        raise EquationError(f"Không thấy model chi tiết in: {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    c = sw.const
    doc, err, _warn = sw.app.OpenDoc6(str(dest), c.swDocPART, c.swOpenDocOptions_Silent, "", 0, 0)
    if doc is None:
        raise EquationError(f"Không mở được bản sao {dest.name} (mã lỗi {err}).")
    model = sw.typed(doc, "IModelDoc2")
    if Path(model.GetPathName()).resolve() != dest.resolve():
        raise EquationError(
            f"SolidWorks trả về '{model.GetPathName()}' thay vì bản sao {dest}; "
            "dừng để không sửa bản gốc."
        )
    return model


def apply(sw: Sw, model, values: dict[str, float]) -> list[str]:
    """Set ``ord_*`` globals on an opened copy and rebuild. Returns rebuild errors."""
    check_names(values)
    eqm = sw.typed(model.GetEquationMgr(), "IEquationMgr")
    if eqm.LinkToFile:
        raise EquationError(
            f"Model dùng equations liên kết file ngoài ({eqm.FilePath}); sửa sẽ đổi cả file chung. "
            "Bỏ liên kết trong SolidWorks rồi thử lại."
        )
    index = global_variables(sw, model)
    missing = [k for k in values if k not in index]
    if missing:
        raise EquationError(f"Model không có biến: {', '.join(missing)}")
    for name, value in values.items():
        eqm.SetEquation(index[name], f'"{name}" = {value:g}')
    eqm.EvaluateAll()
    model.ForceRebuild3(False)
    return feature_errors(sw, model)


def value_of(sw: Sw, model, name: str) -> float:
    eqm = sw.typed(model.GetEquationMgr(), "IEquationMgr")
    return float(eqm.Value(global_variables(sw, model)[name]))
