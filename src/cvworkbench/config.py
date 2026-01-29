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


def resolve_dist_path(config_path: Path) -> Path:
    config = load_config(config_path)
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("Config field paths must be a mapping")

    value = paths.get("dist", "dist")
    return Path(value)


def resolve_runs_path(config_path: Path) -> Path:
    config = load_config(config_path)
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("Config field paths must be a mapping")

    value = paths.get("runs", "runs")
    return Path(value)


def resolve_default_variant(config_path: Path) -> str:
    config = load_config(config_path)
    variants = config.get("variants", {})
    if not isinstance(variants, dict):
        raise ValueError("Config field variants must be a mapping")

    value = variants.get("default")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Config field variants.default is required")

    return value


def resolve_variant_path(variant_id: str, config_path: Path) -> Path:
    if not variant_id.strip():
        raise ValueError("Variant id is required")
    variant_dir = config_path.parent / "variants"
    return variant_dir / f"{variant_id}.yaml"


def resolve_pdf_engine(config_path: Path) -> str | None:
    config = load_config(config_path)
    render = config.get("render", {})
    if not isinstance(render, dict):
        raise ValueError("Config field render must be a mapping")

    value = render.get("pdf_engine")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
