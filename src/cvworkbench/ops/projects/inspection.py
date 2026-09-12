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
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, TypeVar

import yaml

from cvworkbench.ops.projects.artifacts import _inspect_project_artifacts, _regular_artifact
from cvworkbench.ops.projects.manifest import (
    _project_metadata,
    _project_reference,
    _project_relative_path,
    load_project_metadata,
)
from cvworkbench.ops.projects.patches import load_project_patch_payload
from cvworkbench.ops.projects.records import (
    _PROJECT_OPS_RESUME_SURFACE,
    _PROJECT_PATCH_FORMAT_OPS,
    ProjectDetails,
    ProjectError,
    ProjectPatch,
    ProjectProposalIssue,
)
from cvworkbench.variants import Variant, load_variant

_ProposalInput = TypeVar("_ProposalInput", Variant, ProjectPatch)


def project_patch_status(
    *,
    patch_format: str | None,
    patch_is_empty: bool | None,
    patch_line_count: int | None,
) -> str:
    if patch_format is None or patch_is_empty is None or patch_line_count is None:
        return "unavailable"
    if patch_is_empty:
        return "empty"
    if patch_format == _PROJECT_PATCH_FORMAT_OPS:
        suffix = "op" if patch_line_count == 1 else "ops"
        return f"{patch_line_count} {suffix}"
    return f"{patch_line_count} lines"


def project_patch_render_warning(
    *,
    proposal_document_type: str | None,
    patch_operations: tuple[str, ...] | None,
) -> str | None:
    if proposal_document_type != "cover-letter" or patch_operations is None:
        return None
    if not any(operation in _PROJECT_OPS_RESUME_SURFACE for operation in patch_operations):
        return None
    return (
        "project-ops target resume content and will not appear in cover-letter preview/build output"
    )


def load_project_details(project_dir: Path) -> ProjectDetails:
    project_data = load_project_metadata(project_dir)
    spec = _project_reference(project_dir, project_data)
    metadata = _project_metadata(project_dir, project_data)

    proposal_variant, variant_issue = _inspect_proposal_input(
        project_dir, spec.variant_path, "variant", load_variant
    )
    patch, patch_issue = _inspect_proposal_input(
        project_dir, spec.patch_path, "patch", load_project_patch_payload
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
        proposal_variant_id=proposal_variant.id if proposal_variant is not None else None,
        proposal_document_type=proposal_variant.document_type
        if proposal_variant is not None
        else None,
        patch_format=patch.format if patch is not None else None,
        patch_is_empty=len(patch.operations) == 0 if patch is not None else None,
        patch_line_count=len(patch.operations) if patch is not None else None,
        patch_operations=tuple(
            str(operation.get("op", "")).strip() or "<missing-op>" for operation in patch.operations
        )
        if patch is not None
        else None,
        artifact_checks=_inspect_project_artifacts(project_dir, metadata),
        proposal_issues=tuple(issue for issue in (variant_issue, patch_issue) if issue is not None),
    )


def _inspect_proposal_input(
    project_dir: Path,
    path: Path,
    artifact: Literal["variant", "patch"],
    loader: Callable[[Path], _ProposalInput],
) -> tuple[_ProposalInput | None, ProjectProposalIssue | None]:
    try:
        resolved = _regular_artifact(project_dir, path, f"proposal {artifact}")
    except FileNotFoundError:
        return None, ProjectProposalIssue(
            artifact, "missing", f"Proposal {artifact} file is missing: {path}"
        )
    except (OSError, ProjectError) as exc:
        message = (
            str(exc)
            if isinstance(exc, ProjectError)
            else f"Proposal {artifact} file could not be read: {path}"
        )
        return None, ProjectProposalIssue(artifact, "unreadable", message)
    try:
        return loader(resolved), None
    except FileNotFoundError:
        issue = ProjectProposalIssue(
            artifact, "missing", f"Proposal {artifact} file is missing: {path}"
        )
    except (UnicodeError, yaml.YAMLError):
        issue = ProjectProposalIssue(
            artifact, "invalid", f"Proposal {artifact} must contain valid UTF-8 YAML: {path}"
        )
    except ProjectError as exc:
        issue = ProjectProposalIssue(artifact, "invalid", str(exc))
    except ValueError:
        issue = ProjectProposalIssue(
            artifact, "invalid", f"Proposal {artifact} does not satisfy its schema: {path}"
        )
    except OSError:
        issue = ProjectProposalIssue(
            artifact, "unreadable", f"Proposal {artifact} file could not be read: {path}"
        )
    return None, issue


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
