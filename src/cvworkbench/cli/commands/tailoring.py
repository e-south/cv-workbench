"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/commands/tailoring.py

Adapt job ingestion, draft tailoring, and explicit draft application commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cvworkbench.cli.helpers import configure_output_mode
from cvworkbench.cli.output import print_summary
from cvworkbench.config import (
    resolve_project_path,
)
from cvworkbench.ingestion.registry import RegistryError, add_url_context
from cvworkbench.ops.apply import ApplyError, apply_draft
from cvworkbench.ops.projects import (
    ProjectError,
)
from cvworkbench.ops.tailor import DraftPaths, TailorError, tailor_job


def _print_job_add_summary(entry: dict[str, str | Path]) -> None:
    rows = [(key, value) for key, value in entry.items()]
    print_summary("job.add", rows)


def _print_tailor_summary(paths: DraftPaths, output_dir: Path, base_variant: str) -> None:
    print_summary(
        "tailor",
        [
            ("draft_dir", output_dir),
            ("base_variant", base_variant),
            ("variant", paths.variant_path),
            ("patch", paths.patch_path),
            ("job", paths.job_path),
            ("prompt", paths.prompt_path),
        ],
    )


def _print_apply_summary(
    draft_dir: Path,
    patch_path: Path,
    status: str,
    reason: str,
    sot_path: Path,
) -> None:
    print_summary(
        "apply",
        [
            ("draft_dir", draft_dir),
            ("patch", patch_path),
            ("status", status),
            ("reason", reason),
            ("sot_path", sot_path),
        ],
    )


def job_add(
    url: Annotated[
        str,
        typer.Option(
            "--url",
            help="URL to ingest as a context source",
        ),
    ],
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
        entry = add_url_context(url, config)
    except (FileNotFoundError, ValueError, RegistryError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    summary = {
        "context_id": entry.context_id,
        "context_path": entry.path,
        "source": entry.source_path,
        "extracted": entry.extracted_path,
        "signals": entry.signals_path,
        "strategy": entry.strategy_path,
    }
    _print_job_add_summary(summary)


def tailor(
    job: Annotated[
        Path,
        typer.Option(
            "--job",
            help="Path to a job description file",
        ),
    ],
    out: Annotated[
        Path,
        typer.Option(
            "--out",
            help="Output directory for draft files",
        ),
    ],
    base_variant: Annotated[
        str,
        typer.Option(
            "--base-variant",
            help="Base variant id to start from",
        ),
    ] = "base",
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
        resolved_out = resolve_project_path(out, config)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    try:
        paths = tailor_job(
            job_path=job,
            base_variant_id=base_variant,
            output_dir=resolved_out,
            config_path=config,
        )
    except TailorError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_tailor_summary(paths, resolved_out, base_variant)


def apply(
    draft: Annotated[
        Path,
        typer.Option(
            "--draft",
            help="Draft directory containing patch.diff or patch.yaml",
        ),
    ],
    sot_path: Annotated[
        Path,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ],
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
        result = apply_draft(draft_dir=draft, sot_path=sot_path)
    except (ApplyError, ProjectError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_apply_summary(draft, result.patch_path, result.status, result.reason, result.sot_path)
