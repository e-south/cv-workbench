"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/commands/variants.py

Adapt variant inventory, promotion, retention, and cleanup commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

import typer

from cvworkbench.cli.helpers import configure_output_mode
from cvworkbench.cli.output import OutputMode, get_output_mode, print_summary
from cvworkbench.config import (
    resolve_config_path,
    resolve_variant_ttl_days,
)
from cvworkbench.ops.projects import (
    ProjectError,
    load_project,
    resolve_project_dir,
)
from cvworkbench.ops.variant_lifecycle import (
    VariantGcSummary,
    VariantLifecycleError,
    discard_variant,
    gc_variants,
    keep_variant,
    list_variant_inbox,
)
from cvworkbench.ops.variant_promote import PromoteError, promote_variant
from cvworkbench.variants import load_variants_from_config
from cvworkbench.workspace.commands import recipe_command, shell_command
from cvworkbench.workspace.variants import (
    inbox_entry_payload,
    inbox_summary_line,
    variants_summary_line,
)


def _resolve_variant_lifecycle_path(
    *,
    path: Path | None,
    project: str | None,
    config_path: Path,
) -> Path:
    if (path is None) == (project is None):
        raise ValueError("Provide exactly one of --path or --project")
    if project is None:
        return path or Path()
    project_dir = resolve_project_dir(project, config_path)
    spec = load_project(project_dir)
    return spec.variant_path


def _print_variant_promote_summary(variant_id: str, variant_path: Path, status: str) -> None:
    print_summary(
        "variant.promote",
        [
            ("variant_id", variant_id),
            ("variant_path", variant_path),
            ("status", status),
        ],
    )


def _print_variant_keep_summary(variant_id: str, variant_path: Path, status: str) -> None:
    print_summary(
        "variant.keep",
        [
            ("variant_id", variant_id),
            ("variant_path", variant_path),
            ("status", status),
        ],
    )


def _print_variant_discard_summary(variant_path: Path, status: str) -> None:
    print_summary(
        "variant.discard",
        [
            ("variant_path", variant_path),
            ("status", status),
        ],
    )


def _print_variant_gc_summary(summary: VariantGcSummary) -> None:
    candidates = [
        {**asdict(candidate), "cleanup_path": str(candidate.cleanup_path)}
        for candidate in summary.candidates
    ]
    if get_output_mode() == OutputMode.JSON:
        print(
            json.dumps(
                {"command": "variant.gc", **asdict(summary), "candidates": candidates},
                indent=2,
                sort_keys=True,
            )
        )
        return
    print_summary(
        "variant.gc",
        [
            ("expired", str(summary.expired)),
            ("kept_pruned", str(summary.kept_pruned)),
            ("reconciled", str(summary.reconciled)),
            ("status", summary.status),
            (
                "candidates",
                "\n".join(
                    f"{item.action} | {item.reason} | {item.variant_id} | {item.cleanup_path}"
                    for item in summary.candidates
                )
                or "none",
            ),
        ],
    )


def _print_variant_inbox(entries: list[Any], config_path: Path) -> None:
    entry_payload = [inbox_entry_payload(entry, config_path) for entry in entries]
    has_expired_entries = any(item["expired"] for item in entry_payload)
    if get_output_mode() == OutputMode.JSON:
        payload = {
            "command": "variant.inbox",
            "entries": entry_payload,
        }
        if has_expired_entries:
            payload["gc_command"] = recipe_command(
                "variant gc",
                config_path=config_path,
                sot_path=None,
            )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    lines = [
        (
            f"{item['variant_id']} | {item['source']} | {item['status']} | "
            f"{item['expires_at']} | {item['variant_path']}"
        )
        for item in entry_payload
    ]
    rows: list[tuple[str, str | Path]] = [
        ("count", str(len(entry_payload))),
    ]
    if lines:
        rows.append(("entries", "\n".join(lines)))
    if has_expired_entries:
        rows.append(("gc_step", shell_command("variant gc")))
    print_summary("variant.inbox", rows)


def variant_promote(
    draft: Annotated[
        Path,
        typer.Option(
            "--draft",
            help="Draft directory containing variant.yaml",
        ),
    ],
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    variant_id: Annotated[
        str | None,
        typer.Option(
            "--id",
            help="Override the promoted variant id",
        ),
    ] = None,
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
        result = promote_variant(
            draft_dir=draft,
            config_path=config,
            variant_id=variant_id,
        )
    except (PromoteError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_variant_promote_summary(result.variant_id, result.variant_path, result.status)


def variant_list(
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
    config_path = resolve_config_path(config)
    try:
        variants = load_variants_from_config(config_path)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    inbox_entries = list_variant_inbox(config_path)
    inbox_payload = [inbox_entry_payload(entry, config_path) for entry in inbox_entries]
    ttl_days = resolve_variant_ttl_days(config_path)

    payload = {
        "command": "variant.list",
        "variants": variants,
        "ttl_days": ttl_days,
        "inbox": inbox_payload,
        "inbox_count": len(inbox_payload),
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    rows = [
        ("count", str(len(variants))),
        ("variants", variants_summary_line(variants) or "none"),
        ("inbox", inbox_summary_line(inbox_payload)),
        ("ttl_days", str(ttl_days)),
    ]
    print_summary("variant.list", rows)


def variant_inbox(
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
    config_path = resolve_config_path(config)
    try:
        entries = list_variant_inbox(config_path)
    except (VariantLifecycleError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_variant_inbox(entries, config_path)


def variant_keep(
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Path to variant.yaml to promote",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path whose proposal variant should be promoted",
        ),
    ] = None,
    variant_id: Annotated[
        str | None,
        typer.Option(
            "--id",
            help="Override the promoted variant id",
        ),
    ] = None,
    label: Annotated[
        str | None,
        typer.Option(
            "--label",
            help="Checkpoint label for the kept variant",
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
    config_path = resolve_config_path(config)
    if (path is None) == (project is None):
        typer.echo("ERROR: Provide exactly one of --path or --project", err=True)
        raise typer.Exit(code=2)
    try:
        resolved_path = _resolve_variant_lifecycle_path(
            path=path,
            project=project,
            config_path=config_path,
        )
    except (ProjectError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    try:
        result = keep_variant(
            variant_path=resolved_path,
            config_path=config_path,
            variant_id=variant_id,
            label=label,
        )
    except (VariantLifecycleError, FileNotFoundError, ValueError, ProjectError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_variant_keep_summary(result.variant_id, result.variant_path, result.status)


def variant_discard(
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Path to variant.yaml to discard",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path whose proposal variant should be discarded",
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of the draft/proposal artifacts",
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
    config_path = resolve_config_path(config)
    if (path is None) == (project is None):
        typer.echo("ERROR: Provide exactly one of --path or --project", err=True)
        raise typer.Exit(code=2)
    try:
        resolved_path = _resolve_variant_lifecycle_path(
            path=path,
            project=project,
            config_path=config_path,
        )
    except (ProjectError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    try:
        result = discard_variant(
            variant_path=resolved_path,
            config_path=config_path,
            confirm=yes,
        )
    except (VariantLifecycleError, FileNotFoundError, ValueError, ProjectError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_variant_discard_summary(result.variant_path, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


def variant_gc(
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
            help="Confirm deletion of expired draft/proposal artifacts",
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
        summary = gc_variants(config_path=config, confirm=yes)
    except (VariantLifecycleError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_variant_gc_summary(summary)
    if not yes and summary.status == "dry_run":
        raise typer.Exit(code=2)
