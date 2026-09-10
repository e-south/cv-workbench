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


def resolve_project_dir(project: str, config_path: ConfigSource) -> Path:
    candidate = Path(project)
    if candidate.is_absolute() or candidate.exists():
        return candidate
    return resolve_projects_path(config_path) / project


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
