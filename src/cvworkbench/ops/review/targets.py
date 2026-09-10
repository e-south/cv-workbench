"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/review/targets.py

Resolves explicit and project-scoped source runs for review operations.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cvworkbench.config import resolve_runs_path, resolve_sot_path, resolve_variant_path
from cvworkbench.inputs.sot_versions import resolve_active_sot_path
from cvworkbench.ops.projects import (
    ProjectError,
    ProjectPatch,
    ProjectSpec,
    load_project,
    load_project_metadata,
    load_project_patch_payload,
    resolve_project_dir,
)
from cvworkbench.ops.projects.identity import validate_project_id
from cvworkbench.ops.review import ReviewError
from cvworkbench.ops.runs import (
    RunError,
    RunInfo,
    resolve_latest_project_run,
    resolve_latest_run,
    resolve_run,
)
from cvworkbench.variants import Variant, load_variant, validate_variant_id


@dataclass(frozen=True)
class ReviewRun:
    run: RunInfo
    review_dir: Path


@dataclass(frozen=True)
class ReviewTarget:
    run_id: str
    run: RunInfo
    variant: Variant
    review_dir: Path
    sot_path: Path
    project_patch: ProjectPatch | None


def resolve_review_run(
    *,
    config_path: Path,
    run: str | None,
    variant_id: str | None,
    project_dir: Path | None,
) -> ReviewRun:
    if project_dir is not None and variant_id is not None:
        raise ReviewError("--project cannot be combined with --variant")

    if project_dir is not None:
        try:
            project_id = load_project_metadata(project_dir)["id"]
        except ProjectError as exc:
            raise ReviewError(str(exc)) from exc
        try:
            run_info = (
                _resolve_project_run(config_path, project_id, run)
                if run
                else resolve_latest_project_run(config_path, project_id)
            )
        except RunError as exc:
            raise ReviewError(str(exc)) from exc
    elif run:
        try:
            run_info = resolve_run(config_path, run)
        except RunError as exc:
            raise ReviewError(str(exc)) from exc
    else:
        try:
            run_info = resolve_latest_run(
                config_path,
                variant_id=variant_id,
                include_project_runs=False,
            )
        except RunError as exc:
            raise ReviewError(str(exc)) from exc

    try:
        validate_variant_id(run_info.variant_id)
        parts = Path(run_info.run_id).parts
        if len(parts) >= 3 and parts[0] == "projects":
            validate_project_id(parts[1])
            review_dir = Path("projects") / parts[1]
        else:
            review_dir = Path(run_info.variant_id)
    except (ValueError, ProjectError) as exc:
        raise ReviewError(str(exc)) from exc
    return ReviewRun(run=run_info, review_dir=review_dir)


def resolve_review_target(
    *,
    config_path: Path,
    run: str | None,
    variant_id: str | None,
    project_dir: Path | None,
) -> ReviewTarget:
    selection = resolve_review_run(
        config_path=config_path, run=run, variant_id=variant_id, project_dir=project_dir
    )
    run_info = selection.run
    try:
        project = (
            load_project(project_dir)
            if project_dir is not None
            else _load_project_for_run(config_path, run_info.run_id)
        )
        project_patch = (
            load_project_patch_payload(project.patch_path) if project is not None else None
        )
    except ProjectError as exc:
        raise ReviewError(str(exc)) from exc
    if project is not None:
        variant = load_variant(project.variant_path)
        sot_path = resolve_active_sot_path(project.sot_path)
    else:
        variant_path = resolve_variant_path(run_info.variant_id, config_path)
        if not variant_path.exists():
            raise ReviewError(f"Variant not found: {run_info.variant_id}")
        variant = load_variant(variant_path)
        sot_path = resolve_sot_path(None, config_path)

    return ReviewTarget(
        run_id=run_info.run_id,
        run=run_info,
        variant=variant,
        review_dir=selection.review_dir,
        sot_path=sot_path,
        project_patch=project_patch,
    )


def require_run_output(run: RunInfo, fmt: str) -> Path:
    output_name = run.outputs.get(fmt)
    if not output_name:
        raise ReviewError(f"Selected run does not include {fmt} output: {run.run_id}")
    run_root = run.path.resolve()
    path = (run.path / output_name).resolve()
    try:
        path.relative_to(run_root)
    except ValueError as exc:
        raise ReviewError(
            f"Selected run {fmt} output escapes run directory: {output_name}"
        ) from exc
    if not path.exists():
        raise ReviewError(
            f"Selected run is missing immutable {fmt} output: {path}. "
            "Rebuild the target run with the current cv-workbench version."
        )
    return path


def _resolve_project_run(config_path: Path, project_id: str, run: str) -> RunInfo:
    runs_root = resolve_runs_path(config_path)
    project_runs_root = runs_root / "projects" / project_id
    candidate = Path(run)
    try:
        if candidate.exists():
            resolved = resolve_run(config_path, candidate)
        elif (project_runs_root / run).exists():
            resolved = resolve_run(config_path, project_runs_root / run)
        else:
            resolved = resolve_run(config_path, run)
    except RunError as exc:
        raise ReviewError(str(exc)) from exc
    if not resolved.run_id.startswith(f"projects/{project_id}/"):
        raise ReviewError(f"Run does not belong to project: {project_id}")
    return resolved


def _load_project_for_run(config_path: Path, run_id: str) -> ProjectSpec | None:
    parts = Path(run_id).parts
    if len(parts) < 3 or parts[0] != "projects":
        return None
    project_id = parts[1]
    project_dir = resolve_project_dir(project_id, config_path)
    project = load_project(project_dir)
    if project.project_id != project_id:
        raise ProjectError(f"Project identity does not match selected run: {run_id}")
    return project
