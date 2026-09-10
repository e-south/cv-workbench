"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/commands/maintenance.py

Adapt run retention and generated-artifact cleanup commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from cvworkbench.cli.helpers import configure_output_mode
from cvworkbench.cli.output import OutputMode, get_output_mode, print_summary
from cvworkbench.config import (
    resolve_config_path,
    resolve_dist_path,
    resolve_drafts_path,
    resolve_projects_path,
    resolve_registry_path,
    resolve_reviews_path,
    resolve_runs_path,
    resolve_var_root,
)
from cvworkbench.ops.clean import CleanError, clean_path
from cvworkbench.ops.runs import (
    RunError,
    RunGcCandidate,
    RunGcSummary,
    gc_runs,
)
from cvworkbench.workspace.runs import (
    run_payload,
)


def _run_gc_candidate_payload(candidate: RunGcCandidate) -> dict[str, Any]:
    return {
        "run_id": candidate.run_id,
        "path": str(candidate.path),
        "variant_id": candidate.variant_id,
        "created_at": candidate.created_at.isoformat(),
        "reason": candidate.reason,
    }


def _print_runs_gc_summary(summary: RunGcSummary, keep_latest: int, include_invalid: bool) -> None:
    rows = [
        ("status", summary.status),
        ("keep_latest", str(keep_latest)),
        ("candidates", str(len(summary.candidates))),
        ("kept", str(len(summary.kept))),
        ("removed", str(summary.removed)),
    ]
    if include_invalid:
        rows.append(("invalid", str(len(summary.invalid))))
        rows.append(("invalid_candidates", str(len(summary.invalid_candidates))))
    rows.append(
        (
            "retained",
            "\n".join(
                f"{run_id} | {', '.join(reasons)}"
                for run_id, reasons in summary.keep_reasons.items()
            )
            or "none",
        )
    )
    print_summary("runs.gc", rows)


def _print_clean_summary(target: str, path: Path, removed: int, status: str) -> None:
    print_summary(
        "clean",
        [
            ("target", target),
            ("path", path),
            ("removed", str(removed)),
            ("status", status),
        ],
    )


def _require_var_path(target: str, path: Path, config_path: Path) -> None:
    var_root = resolve_var_root(config_path).resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(var_root)
    except ValueError as exc:
        raise CleanError(f"{target} path is outside var: {resolved}") from exc


def runs_gc(
    keep_latest: Annotated[
        int,
        typer.Option(
            "--keep-latest",
            min=0,
            help="Number of most recent runs to keep per project and variant",
        ),
    ] = 1,
    keep: Annotated[
        list[str] | None,
        typer.Option(
            "--keep",
            help="Run id to keep (repeatable)",
        ),
    ] = None,
    include_invalid: Annotated[
        bool,
        typer.Option(
            "--include-invalid",
            help="Delete invalid run directories as part of GC",
        ),
    ] = False,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of selected run artifacts",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        config_path = resolve_config_path(config)
        runs_root = resolve_runs_path(config_path)
        _require_var_path("runs", runs_root, config_path)
        summary = gc_runs(
            config_path=config_path,
            keep_latest=keep_latest,
            keep=keep or [],
            include_invalid=include_invalid,
            confirm=yes,
        )
    except (RunError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    payload = {
        "command": "runs.gc",
        "keep_latest": keep_latest,
        "keep": keep or [],
        "include_invalid": include_invalid,
        "status": summary.status,
        "removed": summary.removed,
        "candidates": [_run_gc_candidate_payload(candidate) for candidate in summary.candidates],
        "kept": [run_payload(run) for run in summary.kept],
        "invalid": [str(path) for path in summary.invalid],
        "invalid_candidates": [str(path) for path in summary.invalid_candidates],
        "keep_reasons": summary.keep_reasons,
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_runs_gc_summary(summary, keep_latest, include_invalid)

    if not yes and summary.status == "dry_run":
        raise typer.Exit(code=2)


def clean_runs(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of all run artifacts",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        config_path = resolve_config_path(config)
        path = resolve_runs_path(config_path)
        _require_var_path("runs", path, config_path)
        result = clean_path(target="runs", path=path, confirm=yes)
    except (CleanError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_clean_summary(result.target, result.path, result.removed, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


def clean_dist(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of all dist artifacts",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        config_path = resolve_config_path(config)
        path = resolve_dist_path(config_path)
        _require_var_path("dist", path, config_path)
        result = clean_path(target="dist", path=path, confirm=yes)
    except (CleanError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_clean_summary(result.target, result.path, result.removed, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


def clean_drafts(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of all draft artifacts",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        config_path = resolve_config_path(config)
        path = resolve_drafts_path(config_path)
        _require_var_path("drafts", path, config_path)
        result = clean_path(target="drafts", path=path, confirm=yes)
    except (CleanError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_clean_summary(result.target, result.path, result.removed, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


def clean_registry(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of all registry artifacts",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        config_path = resolve_config_path(config)
        path = resolve_registry_path(config_path)
        _require_var_path("registry", path, config_path)
        result = clean_path(target="registry", path=path, confirm=yes)
    except (CleanError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_clean_summary(result.target, result.path, result.removed, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


def clean_reviews(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of all review artifacts",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        config_path = resolve_config_path(config)
        path = resolve_reviews_path(config_path)
        _require_var_path("reviews", path, config_path)
        result = clean_path(target="reviews", path=path, confirm=yes)
    except (CleanError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_clean_summary(result.target, result.path, result.removed, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


def clean_projects(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of all project artifacts",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        config_path = resolve_config_path(config)
        path = resolve_projects_path(config_path)
        _require_var_path("projects", path, config_path)
        result = clean_path(target="projects", path=path, confirm=yes)
    except (CleanError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_clean_summary(result.target, result.path, result.removed, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)
