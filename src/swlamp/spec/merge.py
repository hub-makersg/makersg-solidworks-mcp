"""Combine a template with an order's parameters into a resolved :class:`Lamp`.

A template is YAML with a ``params`` block of named defaults. Any string in the rest of
the template may reference them as ``{name}``. A string that is only arithmetic after
substitution (``"{width} - 10"``) becomes a number; anything else stays text.
"""

from __future__ import annotations

import ast
import copy
import operator
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import Lamp, Order

_REF = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_ARITH = re.compile(r"^[0-9.\s+\-*/()]+$")
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


class SpecError(ValueError):
    """A template or order the user must fix; the message says where."""


def _arith(expr: str) -> float:
    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise SpecError(f"Biểu thức không hợp lệ: {expr!r}")

    return ev(ast.parse(expr, mode="eval"))


def _substitute(value: Any, params: dict[str, Any], where: str) -> Any:
    if isinstance(value, dict):
        return {k: _substitute(v, params, f"{where}.{k}") for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, params, f"{where}[{i}]") for i, v in enumerate(value)]
    if not isinstance(value, str) or not _REF.search(value):
        return value
    missing = [n for n in _REF.findall(value) if n not in params]
    if missing:
        raise SpecError(f"{where}: tham số chưa khai báo: {', '.join(missing)}")
    whole = _REF.fullmatch(value)
    if whole:
        return params[whole.group(1)]
    text = _REF.sub(lambda m: str(params[m.group(1)]), value)
    return _arith(text) if _ARITH.match(text) else text


def parse_yaml(text: str, where: str = "YAML") -> dict[str, Any]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SpecError(f"{where}: lỗi cú pháp YAML: {exc}") from None
    if not isinstance(data, dict):
        raise SpecError(f"{where}: YAML phải là một mapping.")
    return data


def load_yaml(path: str | Path) -> dict[str, Any]:
    return parse_yaml(Path(path).read_text(encoding="utf-8"), str(path))


def resolve(template: dict[str, Any], order: Order | dict[str, Any] | None = None) -> Lamp:
    """Return the resolved spec. The template dict is not modified."""
    order = Order.model_validate(order) if isinstance(order, dict) else order
    body = copy.deepcopy(template)
    defaults = body.pop("params", {}) or {}
    overrides = dict(order.params) if order else {}
    unknown = sorted(set(overrides) - set(defaults))
    if unknown:
        raise SpecError(
            "Đơn hàng ghi đè tham số không có trong mẫu: "
            + ", ".join(unknown)
            + f". Tham số của mẫu: {', '.join(sorted(defaults)) or '(không có)'}"
        )
    params = {**defaults, **overrides}
    try:
        return Lamp.model_validate(_substitute(body, params, "template"))
    except ValidationError as exc:
        lines = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()]
        raise SpecError("Spec không hợp lệ:\n" + "\n".join(lines)) from None
