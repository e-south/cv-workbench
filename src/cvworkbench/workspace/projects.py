"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/projects.py

Inspect project inventories, review readiness, and available project commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cvworkbench.config import (
    ConfigSource,
    resolve_projects_path,
)
from cvworkbench.ops.projects import (
    ProjectError,
    load_project_summary,
    suggest_project_variant_id,
)
from cvworkbench.ops.runs import (
    RunError,
    resolve_latest_project_run,
)
from cvworkbench.workspace.commands import recipe_command
from cvworkbench.workspace.runs import invalid_runs_line, run_is_review_ready


def project_commands(
    project_id: str,
    *,
    config_path: Path,
    variant_id: str | None = None,
    review_run_id: str | None = None,
    sot_path: Path | None = None,
) -> dict[str, str]:
    keep_variant_id = suggest_project_variant_id(
        project_id=project_id,
        config_path=config_path,
        preferred_id=variant_id,
    )
    commands = {
        "show": recipe_command(
            f"project show {project_id}",
            config_path=config_path,
            sot_path=None,
        ),
        "preview": recipe_command(
            f"preview --project {project_id}",
            config_path=config_path,
            sot_path=sot_path,
        ),
        "build": recipe_command(
            f"build --project {project_id} --format md,pdf,docx",
            config_path=config_path,
            sot_path=sot_path,
        ),
        "apply": recipe_command(
            f"project apply {project_id}",
            config_path=config_path,
            sot_path=sot_path,
        ),
        "keep": recipe_command(
            f"variant keep --project {project_id} --id {keep_variant_id}",
            config_path=config_path,
            sot_path=None,
        ),
        "discard": recipe_command(
            f"variant discard --project {project_id} --yes",
            config_path=config_path,
            sot_path=None,
        ),
    }
    if review_run_id is not None:
        commands["reviewpack"] = recipe_command(
            f"reviewpack --project {project_id} --run {review_run_id}",
            config_path=config_path,
            sot_path=None,
        )
    return commands


def project_review_payload(project_id: str, config_path: Path) -> dict[str, Any]:
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


def load_project_summaries(config_path: ConfigSource) -> tuple[list[dict[str, Any]], list[Path]]:
    projects_root = resolve_projects_path(config_path)
    if not projects_root.exists():
        return [], []
    summaries: list[dict[str, Any]] = []
    invalid: list[Path] = []
    for path in sorted([p for p in projects_root.iterdir() if p.is_dir()]):
        try:
            project = load_project_summary(path)
        except ProjectError:
            invalid.append(path)
            continue
        summary = {
            "project_id": project.project_id,
            "project_dir": str(project.project_dir),
            "base_variant": project.base_variant_id,
            "created_at": project.created_at,
            "job_source": project.job_source,
        }
        if project.metadata_errors:
            summary["metadata_errors"] = list(project.metadata_errors)
        summaries.append(summary)
    return summaries, invalid


def projects_summary_line(projects: list[dict[str, Any]]) -> str:
    if not projects:
        return "count=0"
    lines = [f"{item['project_id']} ({item['base_variant']})" for item in projects]
    errors = _metadata_error_count(projects)
    if errors:
        lines.append(f"metadata_errors={errors}")
    return f"count={len(projects)}\n" + "\n".join(lines)


def _metadata_error_count(projects: list[dict[str, Any]]) -> int:
    return sum(len(project.get("metadata_errors", [])) for project in projects)


def build_projects_context(
    config_path: ConfigSource,
    *,
    include_items: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    projects, invalid_projects = load_project_summaries(config_path)
    section: dict[str, Any] = {
        "count": len(projects),
        "summary": projects_summary_line(projects),
        "invalid_summary": invalid_runs_line(invalid_projects),
    }
    metadata_errors = _metadata_error_count(projects)
    if metadata_errors:
        section["metadata_error_count"] = metadata_errors
    if include_items:
        section.update(
            {
                "items": projects,
                "invalid": [str(path) for path in invalid_projects],
            }
        )
    return section, projects
