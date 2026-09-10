"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/inspection.py

Inspect project metadata and proposal visibility without mutation.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from cvworkbench.ops.projects.manifest import (
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

    created_at = str(project_data.get("created_at", "")).strip()
    if not created_at:
        raise ProjectError("Project created_at is required")

    job_data = project_data.get("job")
    if not isinstance(job_data, dict):
        raise ProjectError("Project job metadata is invalid")
    source_data = job_data.get("source")
    if not isinstance(source_data, dict):
        raise ProjectError("Project job source metadata is invalid")
    job_source_type = str(source_data.get("type", "")).strip()
    job_source_value = str(source_data.get("value", "")).strip()
    if not job_source_type or not job_source_value:
        raise ProjectError("Project job source metadata is incomplete")

    extracted_path = _project_relative_path(project_dir, job_data.get("extracted_path"))
    raw_value = job_data.get("raw_path")
    raw_path = _project_relative_path(project_dir, raw_value) if raw_value else None

    signals_data = project_data.get("signals")
    if not isinstance(signals_data, dict):
        raise ProjectError("Project signals metadata is invalid")
    signals_path = _project_relative_path(project_dir, signals_data.get("path"))
    signals_hash = str(signals_data.get("hash", "")).strip()
    if not signals_hash:
        raise ProjectError("Project signals hash is required")

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
        created_at=created_at,
        job_source_type=job_source_type,
        job_source_value=job_source_value,
        extracted_path=extracted_path,
        raw_path=raw_path,
        signals_path=signals_path,
        signals_hash=signals_hash,
        proposal_variant_id=proposal_variant_id,
        proposal_document_type=proposal_variant.document_type,
        patch_format=patch.format,
        patch_is_empty=patch_is_empty,
        patch_line_count=patch_line_count,
        patch_operations=patch_operations,
    )
