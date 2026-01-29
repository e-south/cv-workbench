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

from cvworkbench.apply import ApplyError, apply_draft
from cvworkbench.config import (
    resolve_default_variant,
    resolve_dist_path,
    resolve_pdf_engine,
    resolve_sot_path,
    resolve_variant_path,
)
from cvworkbench.diffing import DiffError, DiffSelection, diff_artifacts, parse_artifact
from cvworkbench.paths import filters_dir, output_path
from cvworkbench.pipeline import BuildResult, build_documents
from cvworkbench.rendering import RenderError, render_document
from cvworkbench.syncing import SyncError, SyncResult, sync_site
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


def _echo_kv(key: str, value: str | Path) -> None:
    typer.echo(f"{key}: {value}")


def _print_build_summary(result: BuildResult) -> None:
    _echo_kv("variant", result.variant.id)
    _echo_kv("formats", ",".join(result.formats))
    _echo_kv("outputs_dir", result.dist_dir)
    _echo_kv("run_dir", result.run_dir)
    _echo_kv("canonical", result.canonical_path)
    _echo_kv("resume_json", result.run_dir / "resume.json")
    _echo_kv("manifest_dist", result.dist_dir / "manifest.json")
    _echo_kv("manifest_run", result.run_dir / "manifest.json")
    for fmt in result.formats:
        output_file = output_path(result.dist_dir, result.variant, fmt)
        _echo_kv(f"output_{fmt}", output_file)


def _print_render_summary(
    canonical: Path,
    variant: str,
    dist_dir: Path,
    outputs: dict[str, Path],
) -> None:
    _echo_kv("variant", variant)
    _echo_kv("outputs_dir", dist_dir)
    _echo_kv("canonical", canonical)
    for fmt, path in outputs.items():
        _echo_kv(f"output_{fmt}", path)


def _print_sync_summary(result: SyncResult) -> None:
    plan = result.plan
    changed_files = len(plan.copy_ops)
    if plan.frontmatter_content:
        changed_files += 1
    status = "no_changes"
    if plan.has_changes():
        status = "pr_created" if result.mode == "pr" else "applied"

    _echo_kv("sync_mode", result.mode)
    _echo_kv("sync_status", status)
    _echo_kv("site_repo", result.site.repo_path)
    _echo_kv("pdf_url", plan.pdf_url)
    _echo_kv("files_updated", str(changed_files))
    if result.branch:
        _echo_kv("branch", result.branch)


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
        result = build_documents(
            sot_path=resolved,
            config_path=config,
            variant_id=variant,
            formats=parsed_formats,
        )
    except (ValueError, RenderError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_build_summary(result)


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
    output_files: dict[str, Path] = {}
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
        output_files[fmt] = output_file
    _print_render_summary(canonical, resolved.id, dist_dir, output_files)


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
def apply(
    draft: Annotated[
        Path,
        typer.Option(
            "--draft",
            help="Draft directory containing patch.diff",
        ),
    ],
    sot_path: Annotated[
        Path,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ],
) -> None:
    try:
        apply_draft(draft_dir=draft, sot_path=sot_path)
    except ApplyError as exc:
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
        result = sync_site(
            config_path=config,
            site_config_path=site_config,
            mode=mode,
        )
    except (SyncError, RenderError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_sync_summary(result)
