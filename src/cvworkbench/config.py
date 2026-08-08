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

from cvworkbench.inputs.sot_versions import SotVersionError, resolve_active_sot_path


def load_config(config_path: Path) -> dict[str, Any]:
    config_path = resolve_config_path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text())
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("Config must be a YAML mapping")

    return raw


def resolve_config_path(config_path: Path) -> Path:
    if config_path.is_absolute():
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        return config_path

    if config_path.exists():
        return config_path.resolve()

    resolved = _find_config_in_parents(config_path)
    if resolved is None:
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return resolved


def resolve_sot_path(sot_path: Path | None, config_path: Path) -> Path:
    if sot_path is not None:
        try:
            return resolve_active_sot_path(sot_path)
        except SotVersionError as exc:
            raise ValueError(str(exc)) from exc

    config_path = resolve_config_path(config_path)
    config = load_config(config_path)
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("Config field paths must be a mapping")

    value = paths.get("sot")
    if not value:
        raise ValueError("Config field paths.sot is required when --sot-path is not set")

    resolved = _resolve_from_config(config_path, value)
    try:
        return resolve_active_sot_path(resolved)
    except SotVersionError as exc:
        raise ValueError(str(exc)) from exc


def resolve_dist_path(config_path: Path) -> Path:
    config_path = resolve_config_path(config_path)
    config = load_config(config_path)
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("Config field paths must be a mapping")

    value = paths.get("dist")
    if value:
        return _resolve_from_config(config_path, value)
    return resolve_var_root(config_path) / "dist"


def resolve_publish_path(config_path: Path) -> Path:
    config_path = resolve_config_path(config_path)
    config = load_config(config_path)
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("Config field paths must be a mapping")

    value = paths.get("publish")
    if value:
        return _resolve_from_config(config_path, value)
    return resolve_var_root(config_path) / "publish"


def resolve_runs_path(config_path: Path) -> Path:
    config_path = resolve_config_path(config_path)
    config = load_config(config_path)
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("Config field paths must be a mapping")

    value = paths.get("runs")
    if value:
        return _resolve_from_config(config_path, value)
    return resolve_var_root(config_path) / "runs"


def resolve_registry_path(config_path: Path) -> Path:
    config_path = resolve_config_path(config_path)
    config = load_config(config_path)
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("Config field paths must be a mapping")

    value = paths.get("registry")
    if value:
        return _resolve_from_config(config_path, value)
    return resolve_var_root(config_path) / "registry"


def resolve_drafts_path(config_path: Path) -> Path:
    config_path = resolve_config_path(config_path)
    config = load_config(config_path)
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("Config field paths must be a mapping")

    value = paths.get("drafts")
    if value:
        return _resolve_from_config(config_path, value)
    return resolve_var_root(config_path) / "drafts"


def resolve_reviews_path(config_path: Path) -> Path:
    config_path = resolve_config_path(config_path)
    config = load_config(config_path)
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("Config field paths must be a mapping")

    value = paths.get("reviews")
    if value:
        return _resolve_from_config(config_path, value)
    return resolve_var_root(config_path) / "reviews"


def resolve_projects_path(config_path: Path) -> Path:
    config_path = resolve_config_path(config_path)
    config = load_config(config_path)
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("Config field paths must be a mapping")
    value = paths.get("projects")
    if value is None:
        return resolve_var_root(config_path) / "projects"
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Config field paths.projects must be a string")
    return _resolve_from_config(config_path, value.strip())


def resolve_variant_ttl_days(config_path: Path) -> int:
    config_path = resolve_config_path(config_path)
    config = load_config(config_path)
    lifecycle = config.get("variant_lifecycle", {})
    if not isinstance(lifecycle, dict):
        raise ValueError("Config field variant_lifecycle must be a mapping")
    value = lifecycle.get("ttl_days")
    if not isinstance(value, int) or value <= 0:
        raise ValueError("Config field variant_lifecycle.ttl_days must be a positive integer")
    return value


def resolve_default_variant(config_path: Path) -> str:
    config_path = resolve_config_path(config_path)
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
    config_path = resolve_config_path(config_path)
    variant_dir = config_path.parent / "variants"
    return variant_dir / f"{variant_id}.yaml"


def resolve_pdf_engine(config_path: Path) -> str | None:
    config_path = resolve_config_path(config_path)
    config = load_config(config_path)
    render = config.get("render", {})
    if not isinstance(render, dict):
        raise ValueError("Config field render must be a mapping")

    value = render.get("pdf_engine")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def resolve_themes_dir(config_path: Path) -> Path:
    config_path = resolve_config_path(config_path)
    config = load_config(config_path)
    render = config.get("render", {})
    if not isinstance(render, dict):
        raise ValueError("Config field render must be a mapping")

    value = render.get("themes_dir")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Config field render.themes_dir is required")
    return _resolve_from_config(config_path, value.strip())


def resolve_default_theme(config_path: Path) -> str:
    config_path = resolve_config_path(config_path)
    config = load_config(config_path)
    render = config.get("render", {})
    if not isinstance(render, dict):
        raise ValueError("Config field render must be a mapping")

    value = render.get("theme")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Config field render.theme is required")
    return value.strip()


def resolve_style_preset(config_path: Path) -> str | None:
    config_path = resolve_config_path(config_path)
    config = load_config(config_path)
    render = config.get("render", {})
    if not isinstance(render, dict):
        raise ValueError("Config field render must be a mapping")

    value = render.get("style_preset")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def resolve_sync_mode(config_path: Path) -> str:
    config_path = resolve_config_path(config_path)
    config = load_config(config_path)
    site = config.get("site", {})
    if not isinstance(site, dict):
        raise ValueError("Config field site must be a mapping")
    value = site.get("sync_mode", "local")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Config field site.sync_mode must be a string")
    return value.strip()


def resolve_project_root(config_path: Path) -> Path:
    config_path = resolve_config_path(config_path)
    config_dir = config_path.parent
    if config_dir.name == "config":
        return config_dir.parent.resolve()
    return config_dir.resolve()


def resolve_var_root(config_path: Path) -> Path:
    return resolve_project_root(config_path) / "var"


def resolve_project_path(path: Path, config_path: Path) -> Path:
    if path.is_absolute():
        return path
    return (resolve_project_root(config_path) / path).resolve()


def _resolve_from_config(config_path: Path, value: str) -> Path:
    base = config_path.parent
    path = Path(value)
    if path.is_absolute():
        return path
    return (base / path).resolve()


def _find_config_in_parents(config_path: Path) -> Path | None:
    current = Path.cwd().resolve()
    while True:
        candidate = current / config_path
        if candidate.exists():
            return candidate.resolve()
        if current.parent == current:
            return None
        current = current.parent
