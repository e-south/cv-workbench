"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/config.py

Loads workbench configuration and resolves paths.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from cvworkbench.inputs.sot_versions import SotVersionError, resolve_active_sot_path
from cvworkbench.variants import validate_variant_id


@dataclass(frozen=True)
class ConfigSnapshot:
    path: Path
    content: bytes = field(repr=False)
    data: Mapping[str, Any] = field(init=False, repr=False)
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise TypeError("Configuration content must be immutable bytes")
        if not self.path.is_absolute():
            raise ValueError("Configuration snapshot path must be absolute")
        try:
            raw = yaml.safe_load(self.content.decode())
        except UnicodeDecodeError as exc:
            raise ValueError(f"Config must be UTF-8: {self.path}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"Config is invalid YAML: {self.path}") from exc
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ValueError("Config must be a YAML mapping")
        object.__setattr__(self, "data", _freeze_values(raw, set(), {}))
        object.__setattr__(self, "sha256", hashlib.sha256(self.content).hexdigest())


ConfigSource = Path | ConfigSnapshot


def _freeze_values(value: Any, ancestors: set[int], captured: dict[int, Any]) -> Any:
    if not isinstance(value, (Mapping, list, set)):
        return value
    identity = id(value)
    if identity in ancestors:
        raise ValueError("Config must not contain recursive YAML values")
    if identity in captured:
        return captured[identity]
    ancestors.add(identity)
    try:
        if isinstance(value, Mapping):
            result = MappingProxyType(
                {key: _freeze_values(item, ancestors, captured) for key, item in value.items()}
            )
        elif isinstance(value, list):
            result = tuple(_freeze_values(item, ancestors, captured) for item in value)
        else:
            result = frozenset(_freeze_values(item, ancestors, captured) for item in value)
        captured[identity] = result
        return result
    finally:
        ancestors.remove(identity)


def _mutable_values(value: Any, captured: dict[int, Any]) -> Any:
    if not isinstance(value, (Mapping, tuple, frozenset)):
        return value
    identity = id(value)
    if identity in captured:
        return captured[identity]
    if isinstance(value, Mapping):
        result = {key: _mutable_values(item, captured) for key, item in value.items()}
    elif isinstance(value, tuple):
        result = [_mutable_values(item, captured) for item in value]
    else:
        result = {_mutable_values(item, captured) for item in value}
    captured[identity] = result
    return result


def read_config(config_path: ConfigSource) -> ConfigSnapshot:
    """Capture one workbench configuration generation, or reuse an explicit snapshot."""
    if isinstance(config_path, ConfigSnapshot):
        return config_path
    resolved = resolve_config_path(config_path)
    return ConfigSnapshot(path=resolved, content=resolved.read_bytes())


def load_config(config_path: ConfigSource) -> dict[str, Any]:
    """Return an independent mutable configuration payload."""
    return _mutable_values(read_config(config_path).data, {})


def resolve_publication_variant(config_path: ConfigSource) -> str:
    """Select the declared site publication independently of generated-build defaults."""
    site_path = resolve_config_path(config_path).parent / "site-sync.yaml"
    if not site_path.is_file():
        raise ValueError(
            "Declare site.publish_variant in site-sync.yaml or pass --variant explicitly"
        )
    try:
        raw = yaml.safe_load(site_path.read_text())
    except yaml.YAMLError as exc:
        raise ValueError(f"Site configuration is invalid YAML: {site_path}") from exc
    site = raw.get("site") if isinstance(raw, dict) else None
    value = site.get("publish_variant") if isinstance(site, Mapping) else None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Site configuration must declare a non-empty publish_variant")
    return value.strip()


def resolve_config_path(config_path: ConfigSource) -> Path:
    if isinstance(config_path, ConfigSnapshot):
        return config_path.path
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


def resolve_sot_path(sot_path: Path | None, config_path: ConfigSource) -> Path:
    reference = resolve_sot_reference(sot_path, config_path)
    try:
        return resolve_active_sot_path(reference)
    except SotVersionError as exc:
        raise ValueError(str(exc)) from exc


def resolve_sot_reference(sot_path: Path | None, config_path: ConfigSource) -> Path:
    """Resolve the chosen source location without dereferencing its ACTIVE record."""
    if sot_path is not None:
        return sot_path.resolve()

    configuration = read_config(config_path)
    config_path = configuration.path
    config = configuration.data
    paths = config.get("paths", {})
    if not isinstance(paths, Mapping):
        raise ValueError("Config field paths must be a mapping")

    value = paths.get("sot")
    if not value:
        raise ValueError("Config field paths.sot is required when --sot-path is not set")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Config field paths.sot must be a non-empty string")

    return _resolve_from_config(config_path, value)


def resolve_dist_path(config_path: ConfigSource) -> Path:
    return _artifact_path(config_path, "dist")


def resolve_publish_path(config_path: ConfigSource) -> Path:
    return _artifact_path(config_path, "publish")


def resolve_runs_path(config_path: ConfigSource) -> Path:
    return _artifact_path(config_path, "runs")


def resolve_registry_path(config_path: ConfigSource) -> Path:
    return _artifact_path(config_path, "registry")


def resolve_drafts_path(config_path: ConfigSource) -> Path:
    return _artifact_path(config_path, "drafts")


def resolve_reviews_path(config_path: ConfigSource) -> Path:
    return _artifact_path(config_path, "reviews")


def _artifact_path(config_path: ConfigSource, key: str) -> Path:
    configuration = read_config(config_path)
    paths = configuration.data.get("paths", {})
    if not isinstance(paths, Mapping):
        raise ValueError("Config field paths must be a mapping")
    value = paths.get(key)
    if value is None:
        return resolve_var_root(configuration) / key
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Config field paths.{key} must be a non-empty string")
    return _resolve_from_config(configuration.path, value)


def resolve_projects_path(config_path: ConfigSource) -> Path:
    configuration = read_config(config_path)
    config_path = configuration.path
    config = configuration.data
    paths = config.get("paths", {})
    if not isinstance(paths, Mapping):
        raise ValueError("Config field paths must be a mapping")
    value = paths.get("projects")
    if value is None:
        return resolve_var_root(configuration) / "projects"
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Config field paths.projects must be a string")
    return _resolve_from_config(config_path, value.strip())


def resolve_variant_ttl_days(config_path: ConfigSource) -> int:
    config = read_config(config_path).data
    lifecycle = config.get("variant_lifecycle", {})
    if not isinstance(lifecycle, Mapping):
        raise ValueError("Config field variant_lifecycle must be a mapping")
    value = lifecycle.get("ttl_days")
    if type(value) is not int or value <= 0:
        raise ValueError("Config field variant_lifecycle.ttl_days must be a positive integer")
    return value


def resolve_default_variant(config_path: ConfigSource) -> str:
    config = read_config(config_path).data
    variants = config.get("variants", {})
    if not isinstance(variants, Mapping):
        raise ValueError("Config field variants must be a mapping")

    value = variants.get("default")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Config field variants.default is required")

    return value


def resolve_variant_path(variant_id: str, config_path: ConfigSource) -> Path:
    validate_variant_id(variant_id)
    config_path = resolve_config_path(config_path)
    variant_dir = config_path.parent / "variants"
    return variant_dir / f"{variant_id}.yaml"


def resolve_pdf_engine(config_path: ConfigSource) -> str | None:
    config = read_config(config_path).data
    render = config.get("render", {})
    if not isinstance(render, Mapping):
        raise ValueError("Config field render must be a mapping")

    value = render.get("pdf_engine")
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Config field render.pdf_engine must be a non-empty string")
    return value.strip()


def resolve_themes_dir(config_path: ConfigSource) -> Path:
    configuration = read_config(config_path)
    config_path = configuration.path
    config = configuration.data
    render = config.get("render", {})
    if not isinstance(render, Mapping):
        raise ValueError("Config field render must be a mapping")

    value = render.get("themes_dir")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Config field render.themes_dir is required")
    return _resolve_from_config(config_path, value.strip())


def resolve_default_theme(config_path: ConfigSource) -> str:
    config = read_config(config_path).data
    render = config.get("render", {})
    if not isinstance(render, Mapping):
        raise ValueError("Config field render must be a mapping")

    value = render.get("theme")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Config field render.theme is required")
    return value.strip()


def resolve_style_preset(config_path: ConfigSource) -> str | None:
    config = read_config(config_path).data
    render = config.get("render", {})
    if not isinstance(render, Mapping):
        raise ValueError("Config field render must be a mapping")

    value = render.get("style_preset")
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Config field render.style_preset must be a non-empty string")
    return value.strip()


def resolve_sync_mode(config_path: ConfigSource) -> str:
    config = read_config(config_path).data
    site = config.get("site", {})
    if not isinstance(site, Mapping):
        raise ValueError("Config field site must be a mapping")
    value = site.get("sync_mode", "local")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Config field site.sync_mode must be a string")
    return value.strip()


def resolve_project_root(config_path: ConfigSource) -> Path:
    config_path = resolve_config_path(config_path)
    config_dir = config_path.parent
    if config_dir.name == "config":
        return config_dir.parent.resolve()
    return config_dir.resolve()


def resolve_var_root(config_path: ConfigSource) -> Path:
    return resolve_project_root(config_path) / "var"


def resolve_documents_root(config_path: ConfigSource) -> Path | None:
    """Optional external library; absence does not enable implicit discovery."""
    configuration = read_config(config_path)
    documents = configuration.data.get("documents")
    if documents is None:
        return None
    if not isinstance(documents, Mapping):
        raise ValueError("Config field documents must be a mapping")
    value = documents.get("root")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Config field documents.root must be a non-empty string")
    return _resolve_from_config(configuration.path, value)


def resolve_project_path(path: Path, config_path: ConfigSource) -> Path:
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
