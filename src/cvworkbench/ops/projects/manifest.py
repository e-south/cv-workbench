"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/manifest.py

Read project identity and enforce executable-project prerequisites.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from cvworkbench.ops.projects.identity import validate_project_id
from cvworkbench.ops.projects.records import ProjectError, ProjectSpec
from cvworkbench.variants import validate_variant_id


def load_project_metadata(project_dir: Path) -> dict[str, Any]:
    """Read manifest identity without requiring retained proposal artifacts."""
    if not project_dir.exists():
        raise ProjectError(f"Project directory not found: {project_dir}")
    project_file = project_dir / "project.yaml"
    if not project_file.exists():
        raise ProjectError(f"Project manifest not found: {project_file}")
    try:
        raw = yaml.safe_load(project_file.read_text(encoding="utf-8"))
    except (UnicodeError, yaml.YAMLError) as exc:
        raise ProjectError(
            f"Project manifest must contain valid UTF-8 YAML: {project_file}"
        ) from exc
    except OSError as exc:
        raise ProjectError(f"Project manifest could not be read: {project_file}") from exc
    if not isinstance(raw, dict):
        raise ProjectError("Project manifest must be a mapping")
    project_data = raw.get("project")
    if not isinstance(project_data, dict):
        raise ProjectError("Project manifest is invalid")
    validate_project_id(project_data.get("id"))
    base_variant = project_data.get("base_variant")
    if not base_variant:
        raise ProjectError("Project base_variant is required")
    try:
        validate_variant_id(base_variant)
    except ValueError as exc:
        raise ProjectError(f"Project base_variant is invalid: {exc}") from exc
    return project_data


def load_project(project_dir: Path) -> ProjectSpec:
    return _project_spec(project_dir, load_project_metadata(project_dir))


def _project_spec(project_dir: Path, project_data: dict[str, Any]) -> ProjectSpec:
    sot_path_value = project_data.get("sot_path")
    if not isinstance(sot_path_value, str) or not sot_path_value.strip():
        raise ProjectError("Project sot_path is required")
    sot_path = Path(sot_path_value)
    variant_path = project_dir / "proposals" / "variant.yaml"
    patch_path = project_dir / "proposals" / "patch.yaml"
    if not variant_path.exists():
        raise ProjectError(f"Project variant not found: {variant_path}")
    if not patch_path.exists():
        raise ProjectError(f"Project patch not found: {patch_path}")
    return ProjectSpec(
        project_id=project_data["id"],
        project_dir=project_dir,
        base_variant_id=project_data["base_variant"],
        variant_path=variant_path,
        patch_path=patch_path,
        sot_path=sot_path,
    )


def _project_relative_path(project_dir: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ProjectError("Project manifest path metadata is incomplete")
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (project_dir / candidate)
