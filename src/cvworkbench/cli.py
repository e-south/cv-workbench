"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli.py

Command-line interface for the CV workbench.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

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
from cvworkbench.paths import filters_dir, output_path
from cvworkbench.pipeline import build_documents
from cvworkbench.rendering import RenderError, render_document
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
def tailor() -> None:
    _not_implemented("tailor")


@app.command()
def diff() -> None:
    _not_implemented("diff")


@app.command()
def sync() -> None:
    _not_implemented("sync")
