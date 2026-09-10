"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/inspection.py

Inspect project metadata and proposal visibility without mutation.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cvworkbench.ops.projects.manifest import (
    _project_metadata,
    _project_relative_path,
    _project_spec,
    load_project_metadata,
)
from cvworkbench.ops.projects.patches import _load_project_patch_model
from cvworkbench.ops.projects.records import (
    _PROJECT_OPS_RESUME_SURFACE,
    _PROJECT_PATCH_FORMAT_OPS,
    ProjectDetails,
    ProjectError,
)
from cvworkbench.variants import load_variant


def project_patch_status(
    *,
    patch_format: str,
    patch_is_empty: bool,
    patch_line_count: int,
) -> str:
    if patch_is_empty:
        return "empty"
    if patch_format == _PROJECT_PATCH_FORMAT_OPS:
        suffix = "op" if patch_line_count == 1 else "ops"
        return f"{patch_line_count} {suffix}"
    return f"{patch_line_count} lines"


def project_patch_render_warning(
    *,
    proposal_document_type: str,
    patch_operations: tuple[str, ...],
) -> str | None:
    if proposal_document_type != "cover-letter":
        return None
    if not any(operation in _PROJECT_OPS_RESUME_SURFACE for operation in patch_operations):
        return None
    return (
        "project-ops target resume content and will not appear in cover-letter preview/build output"
    )


def load_project_details(project_dir: Path) -> ProjectDetails:
    project_data = load_project_metadata(project_dir)
    spec = _project_spec(project_dir, project_data)
    metadata = _project_metadata(project_dir, project_data)

    try:
        proposal_variant = load_variant(spec.variant_path)
    except ValueError as exc:
        raise ProjectError(str(exc)) from exc
    proposal_variant_id = proposal_variant.id

    patch = _load_project_patch_model(project_dir)
    patch_is_empty = len(patch.operations) == 0
    patch_line_count = len(patch.operations)
    patch_operations = tuple(
        str(operation.get("op", "")).strip() or "<missing-op>" for operation in patch.operations
    )

    return ProjectDetails(
        spec=spec,
        created_at=metadata.created_at,
        job_source_type=metadata.source.kind,
        job_source_value=metadata.source.value,
        extracted_path=metadata.extracted.path,
        raw_path=metadata.raw_path,
        signals_path=metadata.signals.path,
        signals_hash=metadata.signals.recorded_sha256,
        proposal_variant_id=proposal_variant_id,
        proposal_document_type=proposal_variant.document_type,
        patch_format=patch.format,
        patch_is_empty=patch_is_empty,
        patch_line_count=patch_line_count,
        patch_operations=patch_operations,
    )


def load_project_plan(details: ProjectDetails) -> tuple[dict[str, Any] | None, str | None]:
    """Read optional saved guidance within its project, preserving inspection on error."""
    try:
        path = _project_relative_path(
            details.spec.project_dir,
            str(details.signals_path.parent / "proposal-plan.json"),
            "proposal_plan",
        )
    except ProjectError as exc:
        return None, str(exc)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, None
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON at {path}: {exc.msg}"
    except UnicodeError:
        return None, f"Optional JSON must contain valid UTF-8: {path}"
    except OSError:
        return None, f"Optional JSON could not be read: {path}"
    if not isinstance(raw, dict):
        return None, f"Optional JSON payload must be an object: {path}"
    return raw, None
