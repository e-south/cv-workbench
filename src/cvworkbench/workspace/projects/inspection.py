"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/projects/inspection.py

Inspect project state and its available run review inputs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cvworkbench.config import ConfigSource, read_config
from cvworkbench.ops.projects import (
    ProjectDetails,
    ProjectError,
    inspect_guidance_inputs,
    load_project,
    load_project_details,
    load_project_plan,
    project_patch_render_warning,
    project_patch_status,
    resolve_project_dir,
)
from cvworkbench.ops.runs import RunError, resolve_latest_project_run
from cvworkbench.workspace.projects.commands import project_commands
from cvworkbench.workspace.projects.guidance import (
    guidance_input_context,
    project_artifact_context,
    proposal_input_warning,
    proposal_plan_selection_warning,
)
from cvworkbench.workspace.runs import run_is_review_ready


@dataclass(frozen=True)
class _ProjectInspection:
    details: ProjectDetails
    patch_status: str
    render_warning: str | None
    plan: dict[str, Any] | None
    observations: dict[str, Any]


def _read_project_inspection(
    project_dir: Path, *, config_path: ConfigSource | None, sot_path: Path | None = None
) -> _ProjectInspection:
    details = load_project_details(project_dir)
    render_warning = project_patch_render_warning(
        proposal_document_type=details.proposal_document_type,
        patch_operations=details.patch_operations,
    )
    patch_status = project_patch_status(
        patch_format=details.patch_format,
        patch_is_empty=details.patch_is_empty,
        patch_line_count=details.patch_line_count,
    )
    plan, plan_error = load_project_plan(details)
    observations = project_artifact_context(details.artifact_checks, include_details=True)
    proposal_warning = proposal_input_warning(details.proposal_issues)
    if proposal_warning is not None:
        observations["proposal_warning"] = proposal_warning
    if plan is not None:
        observations.update(
            guidance_input_context(
                inspect_guidance_inputs(
                    plan, details=details, config_path=config_path, sot_path=sot_path
                )
            )
        )
    if plan_error is not None:
        observations["proposal_plan_error"] = plan_error
    plan_warning = proposal_plan_selection_warning(plan, details.spec.base_variant_id)
    if plan_warning is not None:
        observations["proposal_plan_warning"] = plan_warning
    return _ProjectInspection(details, patch_status, render_warning, plan, observations)


def inspect_project(project: str | Path, *, config: ConfigSource) -> dict[str, Any]:
    """Inspect project state, saved guidance, run review inputs, and next commands."""
    configuration = read_config(config)
    project_dir = resolve_project_dir(str(project), configuration)
    state = _read_project_inspection(project_dir, config_path=configuration)
    details = state.details
    review = project_review_payload(details.spec.project_id, configuration)
    commands = project_commands(
        details.spec.project_id,
        config_path=configuration,
        variant_id=details.proposal_variant_id,
        review_run_id=review["run_id"] if review["review_ready"] else None,
        proposal_available=details.proposal_available,
    )
    review["next_command"] = commands.get("reviewpack", commands.get("build"))
    summary = {
        "project": {
            "project_id": details.spec.project_id,
            "project_dir": str(details.spec.project_dir),
            "created_at": details.created_at,
            "base_variant": details.spec.base_variant_id,
            "sot_path": str(details.spec.sot_path),
        },
        "proposal": {
            "status": "available" if details.proposal_available else "unavailable",
            "issues": [
                {"artifact": issue.artifact, "state": issue.state, "error": issue.error}
                for issue in details.proposal_issues
            ],
            "variant_id": details.proposal_variant_id,
            "variant_path": str(details.spec.variant_path),
            "document_type": details.proposal_document_type,
        },
        "job": {
            "source_type": details.job_source_type,
            "source": details.job_source_value,
            "extracted_path": str(details.extracted_path),
            "raw_path": str(details.raw_path) if details.raw_path is not None else None,
        },
        "signals": {"path": str(details.signals_path)},
        "patch": {
            "path": str(details.spec.patch_path),
            "format": details.patch_format,
            "is_empty": details.patch_is_empty,
            "line_count": details.patch_line_count,
            "operations": list(details.patch_operations)
            if details.patch_operations is not None
            else None,
            "render_warning": state.render_warning,
            "status": state.patch_status,
        },
        "review": review,
        "commands": commands,
        **state.observations,
    }
    if state.plan is not None:
        summary["proposal_plan"] = state.plan
    return summary


def _project_error_payload(project_dir: Path, error: str) -> dict[str, Any]:
    project_id = project_dir.name
    try:
        project_id = load_project(project_dir).project_id
    except ProjectError:
        pass
    return {"project_id": project_id, "project_context_error": error}


def inspect_project_preview(
    project_dir: Path, *, config: ConfigSource | None = None, sot_path: Path | None = None
) -> dict[str, Any]:
    """Return preview guidance, preserving an explicit error when details are unavailable."""
    try:
        state = _read_project_inspection(project_dir, config_path=config, sot_path=sot_path)
    except ProjectError as exc:
        return _project_error_payload(project_dir, str(exc))
    details = state.details
    payload: dict[str, Any] = {
        "project_id": details.spec.project_id,
        "proposal_status": "available" if details.proposal_available else "unavailable",
        "proposal_document_type": details.proposal_document_type,
        "patch_status": state.patch_status,
        "patch_operations": list(details.patch_operations)
        if details.patch_operations is not None
        else None,
        "render_warning": state.render_warning,
        **{key: value for key, value in state.observations.items() if key != "job_artifacts"},
    }
    if state.plan is not None:
        payload["recommended_variant"] = state.plan.get("selected_variant")
        payload["recommendation_status"] = state.plan.get("status")
        payload["recommendation_summary"] = state.plan.get("summary")
        missing_values = state.plan.get("job_keywords_missing_in_sot")
        if isinstance(missing_values, list):
            payload["job_keywords_missing"] = [
                str(item).strip()
                for item in missing_values
                if isinstance(item, str) and item.strip()
            ]
        step_values = state.plan.get("steps")
        if isinstance(step_values, list):
            payload["steps"] = [
                str(item).strip() for item in step_values if isinstance(item, str) and item.strip()
            ]
    return payload


def project_review_payload(project_id: str, config_path: ConfigSource) -> dict[str, Any]:
    try:
        latest_run = resolve_latest_project_run(config_path, project_id)
    except RunError:
        return {
            "status": "build_required",
            "review_ready": False,
            "run_id": None,
            "formats": [],
        }

    review_ready = run_is_review_ready(latest_run)
    return {
        "status": "ready" if review_ready else "build_required",
        "review_ready": review_ready,
        "run_id": latest_run.run_id,
        "formats": latest_run.formats,
    }
