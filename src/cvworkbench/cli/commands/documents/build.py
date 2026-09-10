"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/commands/documents/build.py

Adapt document build and canonical-markdown rendering commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cvworkbench.build.formats import normalize_output_formats
from cvworkbench.build.paths import filters_dir, output_path
from cvworkbench.build.pipeline import BuildResult, build_documents, create_run_dir
from cvworkbench.build.rendering import (
    RenderError,
    RenderRequest,
    render_documents,
    resolve_filter_paths,
)
from cvworkbench.build.styles import prepare_html_style
from cvworkbench.cli.helpers import _validate_sot, configure_output_mode
from cvworkbench.cli.output import print_summary
from cvworkbench.config import (
    read_config,
    resolve_default_theme,
    resolve_default_variant,
    resolve_dist_path,
    resolve_pdf_engine,
    resolve_runs_path,
    resolve_sot_path,
    resolve_style_preset,
    resolve_themes_dir,
    resolve_variant_path,
)
from cvworkbench.inputs.sot_versions import (
    SotVersionError,
    resolve_active_sot_path,
)
from cvworkbench.ops.projects import (
    ProjectError,
    load_project,
    prepare_project_sot,
    resolve_project_dir,
)
from cvworkbench.themes import (
    ThemeError,
    build_render_plan,
    resolve_theme,
)
from cvworkbench.variants import load_variant


def _parse_formats(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    formats: list[str] = []
    for value in values:
        parts = [part.strip() for part in value.split(",") if part.strip()]
        formats.extend(parts)
    normalized = normalize_output_formats(formats)
    return [] if normalized is None else normalized


def _print_build_summary(result: BuildResult) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("variant", result.variant.id),
        ("formats", ",".join(result.formats)),
        ("outputs_dir", result.dist_dir),
        ("run_dir", result.run_dir),
        ("canonical", result.canonical_path),
        ("resume_json", result.run_dir / "resume.json"),
        ("manifest_dist", result.dist_dir / "manifest.json"),
        ("manifest_run", result.run_dir / "manifest.json"),
    ]
    if result.theme_id:
        rows.append(("theme", result.theme_id))
    if result.style_preset:
        rows.append(("style_preset", result.style_preset))
    for fmt in result.formats:
        output_file = output_path(result.dist_dir, result.variant, fmt)
        rows.append((f"output_{fmt}", output_file))
    print_summary("build", rows)


def _print_render_summary(
    canonical: Path,
    variant: str,
    dist_dir: Path,
    outputs: dict[str, Path],
) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("variant", variant),
        ("outputs_dir", dist_dir),
        ("canonical", canonical),
    ]
    for fmt, path in outputs.items():
        rows.append((f"output_{fmt}", path))
    print_summary("render", rows)


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
            help="Variant id to build; cannot be combined with --project",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path; cannot be combined with --variant",
        ),
    ] = None,
    formats: Annotated[
        list[str] | None,
        typer.Option(
            "--format",
            help="Output formats to render (repeatable or comma-separated)",
        ),
    ] = None,
    theme: Annotated[
        str | None,
        typer.Option(
            "--theme",
            help="Theme id to use for rendering",
        ),
    ] = None,
    style_preset: Annotated[
        str | None,
        typer.Option(
            "--style-preset",
            help="Style preset to apply",
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
        configuration = read_config(config)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    project_spec = None
    variant_path_override = None
    run_dir = None
    if project:
        project_dir = resolve_project_dir(project, configuration)
        try:
            project_spec = load_project(project_dir)
        except ProjectError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        if variant:
            typer.echo("ERROR: --variant cannot be combined with --project", err=True)
            raise typer.Exit(code=2)
        variant_path_override = project_spec.variant_path
        try:
            resolved = resolve_active_sot_path(project_spec.sot_path)
        except SotVersionError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        if sot_path is not None:
            try:
                resolved = resolve_sot_path(sot_path, configuration)
            except (FileNotFoundError, ValueError) as exc:
                typer.echo(f"ERROR: {exc}", err=True)
                raise typer.Exit(code=1) from exc
        runs_root = resolve_runs_path(configuration) / "projects" / project_spec.project_id
        runs_root.mkdir(parents=True, exist_ok=True)
        run_dir = create_run_dir(runs_root)
        try:
            resolved = prepare_project_sot(
                project_dir=project_spec.project_dir,
                sot_path=resolved,
                target_dir=run_dir / "sot",
            )
        except ProjectError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    else:
        try:
            resolved = resolve_sot_path(sot_path, configuration)
        except (FileNotFoundError, ValueError) as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    errors = _validate_sot(resolved)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)

    parsed_formats = _parse_formats(formats)
    try:
        result = build_documents(
            sot_path=resolved,
            config_path=configuration,
            variant_id=variant,
            formats=parsed_formats,
            theme=theme,
            style_preset=style_preset,
            variant_path_override=variant_path_override,
            run_dir=run_dir,
            dist_dir=run_dir if project_spec is not None else None,
        )
    except (ValueError, RenderError, ThemeError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_build_summary(result)


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
    theme: Annotated[
        str | None,
        typer.Option(
            "--theme",
            help="Theme id to use for rendering",
        ),
    ] = None,
    style_preset: Annotated[
        str | None,
        typer.Option(
            "--style-preset",
            help="Style preset to apply",
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
    if not canonical.exists():
        typer.echo(f"ERROR: Canonical markdown not found: {canonical}", err=True)
        raise typer.Exit(code=1)

    try:
        configuration = read_config(config)
        resolved_variant = variant or resolve_default_variant(configuration)
        variant_path = resolve_variant_path(resolved_variant, configuration)
        resolved = load_variant(variant_path)
        dist_dir = resolve_dist_path(configuration) / resolved.id
        pdf_engine = resolve_pdf_engine(configuration)
        theme_id = theme or resolved.render_theme or resolve_default_theme(configuration)
        preset = style_preset or resolved.render_style_preset or resolve_style_preset(configuration)
        theme_dir = resolve_themes_dir(configuration)
        theme_obj = resolve_theme(theme_dir, theme_id)
    except (FileNotFoundError, ValueError, ThemeError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    parsed_formats = _parse_formats(formats)
    selected_formats = resolved.outputs if parsed_formats is None else parsed_formats
    parsed_formats = normalize_output_formats(selected_formats)
    if not parsed_formats:
        typer.echo("ERROR: No output formats selected", err=True)
        raise typer.Exit(code=1)
    try:
        render_plans = {
            fmt: build_render_plan(
                output_format=fmt, theme=theme_obj, style_preset=preset, pdf_engine=pdf_engine
            )
            for fmt in parsed_formats
        }
    except (RenderError, ThemeError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    dist_dir.mkdir(parents=True, exist_ok=True)
    filters_path = filters_dir()
    resolved_filter_paths = resolve_filter_paths(filters_path)
    render_requests: list[RenderRequest] = []
    output_files: dict[str, Path] = {}
    for fmt in parsed_formats:
        output_file = output_path(dist_dir, resolved, fmt)
        try:
            plan = render_plans[fmt]
            if fmt == "html":
                plan = prepare_html_style(dist_dir, plan, theme_obj.id, preset)
            render_requests.append(
                RenderRequest(
                    input_path=canonical,
                    output_path=output_file,
                    variant=resolved,
                    filters_dir=filters_path,
                    output_format=fmt,
                    pdf_engine=pdf_engine,
                    render_plan=plan,
                )
            )
        except (RenderError, ThemeError) as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    def _record_render_success(request: RenderRequest) -> None:
        output_files[request.output_format] = request.output_path

    try:
        render_documents(
            render_requests,
            filter_paths=resolved_filter_paths,
            after_each_success=_record_render_success,
        )
    except RenderError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_render_summary(canonical, resolved.id, dist_dir, output_files)
