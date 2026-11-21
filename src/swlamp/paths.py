"""Order folders and the guard that keeps every order write inside its folder."""

from __future__ import annotations

from pathlib import Path


class PathEscape(PermissionError):
    pass


def new_order_dir(root: Path, order_id: str) -> Path:
    """Create a fresh folder for the order; never reuse or overwrite an earlier run."""
    root.mkdir(parents=True, exist_ok=True)
    for n in range(1, 1000):
        candidate = root / (order_id if n == 1 else f"{order_id}-{n}")
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"Quá nhiều thư mục cho đơn {order_id} trong {root}.")


class Guard:
    """Resolves names inside one order folder and refuses anything that escapes it."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder.resolve()

    def path(self, name: str | Path) -> Path:
        p = (self.folder / name).resolve()
        if p != self.folder and self.folder not in p.parents:
            raise PathEscape(f"Từ chối ghi ra ngoài thư mục đơn: {name}")
        return p
