"""Where swlamp keeps its files. Each location can be moved with an environment variable."""

from __future__ import annotations

import os
from pathlib import Path


def config_dir() -> Path:
    """User configuration directory (holds the K-factor table)."""
    env = os.environ.get("SWLAMP_CONFIG_DIR")
    if env:
        return Path(env)
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "swlamp"


def output_root() -> Path:
    """Directory under which every order gets its own folder."""
    env = os.environ.get("SWLAMP_OUTPUT_DIR")
    return Path(env) if env else Path.home() / "Documents" / "swlamp-orders"


def script_tool_enabled() -> bool:
    return os.environ.get("SWLAMP_ENABLE_SCRIPT") == "1"
