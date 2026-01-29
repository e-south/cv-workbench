"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/config.py

Loads workbench configuration and resolves paths.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text())
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("Config must be a YAML mapping")

    return raw


def resolve_sot_path(sot_path: Path | None, config_path: Path) -> Path:
    if sot_path is not None:
        return sot_path

    config = load_config(config_path)
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("Config field paths must be a mapping")

    value = paths.get("sot")
    if not value:
        raise ValueError("Config field paths.sot is required when --sot-path is not set")

    return Path(value)
