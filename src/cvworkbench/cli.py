"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli.py

Command-line interface for the CV workbench.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from cvworkbench.config import (
    resolve_default_variant,
    resolve_dist_path,
    resolve_pdf_engine,
    resolve_sot_path,
    resolve_variant_path,
)
from cvworkbench.diffing import DiffError, DiffSelection, diff_artifacts, parse_artifact
from cvworkbench.paths import filters_dir, output_path
from cvworkbench.pipeline import build_documents
from cvworkbench.rendering import RenderError, render_document
from cvworkbench.syncing import SyncError, sync_site
from cvworkbench.tailor import TailorError, tailor_job
from cvworkbench.validation import validate_sot
from cvworkbench.variants import load_variant

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _not_implemented(command: str) -> None:
    typer.echo(f"{command} is not implemented yet", err=True)
    raise typer.Exit(code=2)


def _parse_formats(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    formats: list[str] = []
    for value in values:
        parts = [part.strip() for part in value.split(",") if part.strip()]
        formats.extend(parts)
    return formats


@app.command()
def validate(
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
) -> None:
    try:
        resolved = resolve_sot_path(sot_path, config)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    errors = validate_sot(resolved)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)


@app.command()
def build(
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
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id to build",
        ),
    ] = None,
    formats: Annotated[
        list[str] | None,
        typer.Option(
            "--format",
            help="Output formats to render (repeatable or comma-separated)",
        ),
    ] = None,
) -> None:
    try:
        resolved = resolve_sot_path(sot_path, config)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    errors = validate_sot(resolved)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)

    parsed_formats = _parse_formats(formats)
    try:
        build_documents(
            sot_path=resolved,
            config_path=config,
            variant_id=variant,
            formats=parsed_formats,
        )
    except (ValueError, RenderError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def render(
    canonical: Annotated[
        Path,
        typer.Option(
            "--canonical",
            help="Path to canonical markdown input",
        ),
    ],
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id to render",
        ),
    ] = None,
    formats: Annotated[
        list[str] | None,
        typer.Option(
            "--format",
            help="Output formats to render (repeatable or comma-separated)",
        ),
    ] = None,
) -> None:
    if not canonical.exists():
        typer.echo(f"ERROR: Canonical markdown not found: {canonical}", err=True)
        raise typer.Exit(code=1)

    try:
        resolved_variant = variant or resolve_default_variant(config)
        variant_path = resolve_variant_path(resolved_variant, config)
        resolved = load_variant(variant_path)
        dist_dir = resolve_dist_path(config) / resolved.id
        dist_dir.mkdir(parents=True, exist_ok=True)
        pdf_engine = resolve_pdf_engine(config)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    parsed_formats = _parse_formats(formats) or resolved.outputs
    filters_path = filters_dir()
    for fmt in parsed_formats:
        output_file = output_path(dist_dir, resolved, fmt)
        try:
            render_document(
                canonical,
                output_file,
                resolved,
                filters_path,
                fmt,
                pdf_engine,
            )
        except RenderError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc


@app.command()
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
) -> None:
    try:
        tailor_job(
            job_path=job,
            base_variant_id=base_variant,
            output_dir=out,
            config_path=config,
        )
    except TailorError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def diff(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    artifact: Annotated[
        str | None,
        typer.Option(
            "--artifact",
            help="Artifact type (rendered, canonical, resume) with optional :format",
        ),
    ] = None,
    artifact_a: Annotated[
        str | None,
        typer.Option(
            "--artifact-a",
            help="Artifact type for side A",
        ),
    ] = None,
    artifact_b: Annotated[
        str | None,
        typer.Option(
            "--artifact-b",
            help="Artifact type for side B",
        ),
    ] = None,
    run: Annotated[
        str | None,
        typer.Option(
            "--run",
            help="Run id or path to use for both sides",
        ),
    ] = None,
    run_a: Annotated[
        str | None,
        typer.Option(
            "--run-a",
            help="Run id or path for side A",
        ),
    ] = None,
    run_b: Annotated[
        str | None,
        typer.Option(
            "--run-b",
            help="Run id or path for side B",
        ),
    ] = None,
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id for both sides",
        ),
    ] = None,
    variant_a: Annotated[
        str | None,
        typer.Option(
            "--variant-a",
            help="Variant id for side A",
        ),
    ] = None,
    variant_b: Annotated[
        str | None,
        typer.Option(
            "--variant-b",
            help="Variant id for side B",
        ),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Output format: unified or json",
        ),
    ] = "unified",
) -> None:
    selection_a = DiffSelection(
        artifact=parse_artifact(artifact_a or artifact),
        run=run_a or run,
        variant=variant_a or variant,
    )
    selection_b = DiffSelection(
        artifact=parse_artifact(artifact_b or artifact),
        run=run_b or run,
        variant=variant_b or variant,
    )

    try:
        diff_text, summary = diff_artifacts(
            config_path=config,
            selection_a=selection_a,
            selection_b=selection_b,
        )
    except DiffError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if output_format == "json":
        typer.echo(json.dumps(summary, indent=2, sort_keys=True))
        return

    if output_format != "unified":
        typer.echo(f"ERROR: Unknown output format: {output_format}", err=True)
        raise typer.Exit(code=1)

    if diff_text:
        typer.echo(diff_text)


@app.command()
def sync(
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            help="Sync mode: pr or local",
        ),
    ] = "pr",
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    site_config: Annotated[
        Path,
        typer.Option(
            "--site-config",
            help="Path to site sync config",
        ),
    ] = Path("config/site-sync.yaml"),
) -> None:
    try:
        sync_site(
            config_path=config,
            site_config_path=site_config,
            mode=mode,
        )
    except (SyncError, RenderError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
