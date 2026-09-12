"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/commands/workspace.py

Present workspace status, context, bootstrap, and workflow guidance.

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
from cvworkbench.ops.runs import (
    RunError,
)
from cvworkbench.ops.variant_lifecycle import (
    VariantLifecycleError,
)
from cvworkbench.workspace.context import inspect_workspace
from cvworkbench.workspace.status import StatusInspectionError, inspect_status


def _print_status_summary(summary: dict[str, Any]) -> None:
    rows = [
        ("sot_path", summary["sot"]["path"]),
        ("sot_files", summary["sot"]["files_summary"]),
        ("sot_sections", summary["sot"]["sections_summary"]),
        ("sot_tags_top", summary["sot"]["tags_summary"]),
        ("variants", summary["variants"]["summary"]),
        ("variant_inbox", summary["variants"]["inbox_summary"]),
        ("variant_ttl_days", summary["variants"]["ttl_days"]),
        ("runs_latest", summary["runs"]["latest_summary"]),
        ("runs_recent", summary["runs"]["recents_summary"]),
        ("projects", summary["projects"]["summary"]),
        ("publication", summary["publication"]["state"]),
        ("reviews", summary["reviews"]["summary"]),
    ]
    if summary["runs"]["invalid_summary"]:
        rows.append(("runs_invalid", summary["runs"]["invalid_summary"]))
    if summary["projects"]["invalid_summary"]:
        rows.append(("projects_invalid", summary["projects"]["invalid_summary"]))
    if summary["sot"]["versions_summary"]:
        rows.append(("sot_versions", summary["sot"]["versions_summary"]))
    print_summary("status", rows)


def _print_context_summary(summary: dict[str, Any]) -> None:
    sot_path = summary["sot"]["path"] or summary["sot"]["configured_path"] or "none"
    recommended = summary["recommended_workflows"]
    rows = [
        ("config", summary["config"]["path"]),
        ("publication", summary["publication"]["state"]),
        ("sot_status", summary["sot"]["status"]),
        ("sot_path", sot_path),
        ("variants", summary["variants"]["summary"]),
        ("runs_latest", summary["runs"]["latest_summary"]),
        ("projects", summary["projects"]["summary"]),
        ("reviews", summary["reviews"]["summary"]),
        (
            "next_workflows",
            ", ".join([workflow["id"] for workflow in recommended]) or "none",
        ),
        (
            "next_commands",
            "\n".join([f"{workflow['id']}: {workflow['command']}" for workflow in recommended])
            or "none",
        ),
        ("recipes", ", ".join([recipe["id"] for recipe in summary["recipes"]])),
    ]
    if summary["issues"]:
        rows.append(("issues", "; ".join(summary["issues"])))
    print_summary("context", rows)


def _print_bootstrap_summary(summary: dict[str, Any]) -> None:
    sot_path = summary["sot"]["path"] or summary["sot"]["configured_path"] or "none"
    recommended = summary["recommended_workflows"]
    rows = [
        ("config", summary["config"]["path"]),
        ("sot_status", summary["sot"]["status"]),
        ("sot_path", sot_path),
        ("variants", summary["variants"]["summary"]),
        ("runs_latest", summary["runs"]["latest_summary"]),
        (
            "next_workflows",
            ", ".join([workflow["id"] for workflow in recommended]) or "none",
        ),
        (
            "next_commands",
            "\n".join([f"{workflow['id']}: {workflow['command']}" for workflow in recommended])
            or "none",
        ),
    ]
    if summary["issues"]:
        rows.append(("issues", "; ".join(summary["issues"])))
    print_summary("bootstrap", rows)


def _format_workflow_list(items: list[str]) -> str:
    if not items:
        return "none"
    return "\n".join(f"- {item}" for item in items)


def _format_workflow_steps(steps: list[dict[str, Any]]) -> str:
    if not steps:
        return "none"
    lines: list[str] = []
    for index, step in enumerate(steps, start=1):
        lines.append(f"{index}. {step['command']}")
        description = step.get("description")
        if description:
            lines.append(f"   {description}")
    return "\n".join(lines)


def _print_workflow_summary(
    *,
    recipes: list[dict[str, Any]],
    sot_status: str,
    issues: list[str],
    selected_recipe: str | None,
) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("sot_status", sot_status),
        ("recipes", str(len(recipes))),
    ]
    if selected_recipe:
        rows.append(("selected", selected_recipe))
    if issues:
        rows.append(("issues", "; ".join(issues)))
    print_summary("workflow", rows)

    for index, recipe in enumerate(recipes):
        print_summary(
            f"workflow.{recipe['id']}",
            [
                ("recipe_id", recipe["id"]),
                ("title", recipe["title"]),
                ("preconditions", _format_workflow_list(recipe["preconditions"])),
                ("steps", _format_workflow_steps(recipe["steps"])),
                ("outputs", _format_workflow_list(recipe["outputs"])),
                ("stop_conditions", _format_workflow_list(recipe["stop_conditions"])),
            ],
        )
        if get_output_mode() == OutputMode.PLAIN and index < len(recipes) - 1:
            print("")


def _compact_context_payload(summary: dict[str, Any]) -> dict[str, Any]:
    """Present an inspection requested with compact=True."""
    return {
        "config": summary["config"],
        "publication": summary["publication"],
        "documents": summary["documents"],
        "sot": {
            "configured_path": summary["sot"]["configured_path"],
            "path": summary["sot"]["path"],
            "status": summary["sot"]["status"],
            "errors": summary["sot"]["errors"],
            "files_summary": summary["sot"]["files_summary"],
            "sections_summary": summary["sot"]["sections_summary"],
            "tags_summary": summary["sot"]["tags_summary"],
            "versions_summary": summary["sot"]["versions_summary"],
        },
        "variants": {
            "default": summary["variants"]["default"],
            "config_count": summary["variants"]["config_count"],
            "summary": summary["variants"]["summary"],
            "inbox_count": summary["variants"]["inbox_count"],
            "inbox_summary": summary["variants"]["inbox_summary"],
            "ttl_days": summary["variants"]["ttl_days"],
        },
        "runs": {
            "latest_summary": summary["runs"]["latest_summary"],
            "invalid_summary": summary["runs"]["invalid_summary"],
        },
        "projects": summary["projects"],
        "reviews": {
            "count": summary["reviews"]["count"],
            "summary": summary["reviews"]["summary"],
        },
        "recipes": [
            {"id": recipe["id"], "title": recipe["title"]} for recipe in summary["recipes"]
        ],
        "recommended_workflows": summary["recommended_workflows"],
        "issues": summary["issues"],
    }


def _compact_workflow_payload(
    summary: dict[str, Any], recipes: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "config": summary["config"],
        "sot": {
            "configured_path": summary["sot"]["configured_path"],
            "path": summary["sot"]["path"],
            "status": summary["sot"]["status"],
            "errors": summary["sot"]["errors"],
        },
        "recipes": recipes,
        "issues": summary["issues"],
    }


def status(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
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
        summary = inspect_status(config=config, sot_path=sot_path)
    except StatusInspectionError as exc:
        for error in exc.errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1) from exc
    except (OSError, ValueError, RunError, VariantLifecycleError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"command": "status", **summary}, indent=2, sort_keys=True))
        return

    _print_status_summary(summary)


def bootstrap(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
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
        summary = inspect_workspace(
            sot_path=sot_path,
            strict=False,
            config=config,
            compact=True,
        )
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if get_output_mode() == OutputMode.JSON:
        payload = _compact_context_payload(summary)
        typer.echo(json.dumps({"command": "bootstrap", **payload}, indent=2, sort_keys=True))
        return

    _print_bootstrap_summary(summary)


def context(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Fail fast when required inputs are missing",
        ),
    ] = False,
    compact: Annotated[
        bool,
        typer.Option(
            "--compact",
            help="Use summary-only JSON output for bootstrap, logs, and agent handoff",
        ),
    ] = False,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
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
    if compact and get_output_mode() != OutputMode.JSON:
        typer.echo("ERROR: --compact requires --json", err=True)
        raise typer.Exit(code=2)
    try:
        summary = inspect_workspace(
            sot_path=sot_path,
            strict=strict,
            config=config,
            compact=compact,
        )
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if get_output_mode() == OutputMode.JSON:
        payload = _compact_context_payload(summary) if compact else summary
        typer.echo(json.dumps({"command": "context", **payload}, indent=2, sort_keys=True))
        return

    _print_context_summary(summary)


def workflow(
    recipe_id: Annotated[
        str | None,
        typer.Option(
            "--id",
            help="Show only one workflow recipe by id",
        ),
    ] = None,
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
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
    compact: Annotated[
        bool,
        typer.Option(
            "--compact",
            help="Use summary-only JSON output for recipe retrieval and agent handoff",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    if compact and get_output_mode() != OutputMode.JSON:
        typer.echo("ERROR: --compact requires --json", err=True)
        raise typer.Exit(code=2)
    try:
        summary = inspect_workspace(
            sot_path=sot_path,
            strict=False,
            config=config,
            compact=compact,
        )
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    recipes = summary["recipes"]
    if recipe_id is not None:
        recipes = [recipe for recipe in recipes if recipe["id"] == recipe_id]
        if not recipes:
            typer.echo(f"ERROR: Unknown workflow id: {recipe_id}", err=True)
            raise typer.Exit(code=1)

    payload = {
        "config": summary["config"],
        "sot": summary["sot"],
        "recipes": recipes,
        "issues": summary["issues"],
    }

    if get_output_mode() == OutputMode.JSON:
        if compact:
            payload = _compact_workflow_payload(summary, recipes)
        typer.echo(json.dumps({"command": "workflow", **payload}, indent=2, sort_keys=True))
        return

    _print_workflow_summary(
        recipes=recipes,
        sot_status=summary["sot"]["status"],
        issues=summary["issues"],
        selected_recipe=recipe_id,
    )
