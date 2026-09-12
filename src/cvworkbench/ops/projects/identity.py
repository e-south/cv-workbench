"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/identity.py

Resolve project selectors and allocate proposal identities.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from cvworkbench.config import (
    ConfigSource,
    resolve_projects_path,
    resolve_variant_path,
)
from cvworkbench.ops.projects.records import ProjectError


def validate_project_id(project_id: object) -> None:
    if not project_id:
        raise ProjectError("Project id is required")
    if (
        not isinstance(project_id, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", project_id) is None
    ):
        raise ProjectError(
            "Project id must start with a letter or number and contain only letters, numbers, '.', '_' or '-'"
        )


def resolve_project_dir(project: str | Path, config_path: ConfigSource) -> Path:
    """Resolve IDs in the configured store and explicit paths from the caller's directory."""
    if isinstance(project, str):
        if not project.strip():
            raise ProjectError("Project selector is required")
        candidate = Path(project)
        explicit_path = (
            candidate.is_absolute() or project in {".", ".."} or project != candidate.name
        )
        if not explicit_path:
            validate_project_id(project)
            candidate = resolve_projects_path(config_path) / project
    elif isinstance(project, Path):
        candidate = project
    else:
        raise ProjectError("Project selector must be a string or Path")
    try:
        return candidate.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProjectError("Project path could not be resolved") from exc


def suggest_project_variant_id(
    *,
    project_id: str,
    config_path: ConfigSource,
    preferred_id: str | None = None,
) -> str:
    candidate = (preferred_id or "").strip()
    if (
        candidate
        and candidate != "base"
        and not resolve_variant_path(candidate, config_path).exists()
    ):
        return candidate
    base = _slugify(f"proposal-{project_id}") or "proposal"
    for suffix in range(0, 1000):
        candidate = base if suffix == 0 else f"{base}-{suffix:02d}"
        if not resolve_variant_path(candidate, config_path).exists():
            return candidate
    raise ProjectError(f"Could not allocate project proposal variant id for: {project_id}")


def _project_id_from_url(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return f"project-{digest[:8]}"


def _slugify(value: str) -> str:
    if not isinstance(value, str):
        raise ProjectError("Project slug must be a string")
    cleaned: list[str] = []
    for char in value.lower():
        if char.isalnum():
            cleaned.append(char)
        else:
            cleaned.append("-")
    slug = "".join(cleaned)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")
