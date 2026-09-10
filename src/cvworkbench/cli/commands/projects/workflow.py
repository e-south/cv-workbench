"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/commands/projects/workflow.py

Adapt project creation, inspection, and explicit application commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from cvworkbench.cli.commands.preview import dev_serve
from cvworkbench.cli.commands.projects.presentation import (
    _print_project_apply_summary,
    _print_project_new_summary,
    _print_project_show_summary,
    _project_summary_payload,
)
from cvworkbench.cli.helpers import configure_output_mode
from cvworkbench.cli.output import OutputMode, get_output_mode
from cvworkbench.config import (
    resolve_config_path,
    resolve_default_variant,
    resolve_sot_path,
)
from cvworkbench.ops.projects import (
    ProjectError,
    apply_project_patch,
    create_project_from_file,
    create_project_from_url,
    load_project,
    resolve_project_dir,
)
from cvworkbench.variants import load_variant
from cvworkbench.workspace.projects import (
    inspect_project,
)


def project_new(
    job_url: Annotated[
        str | None,
        typer.Option(
            "--job-url",
            help="Job URL to ingest",
        ),
    ] = None,
    job_file: Annotated[
        Path | None,
        typer.Option(
            "--job-file",
            help="Job description file",
        ),
    ] = None,
    slug: Annotated[
        str | None,
        typer.Option(
            "--slug",
            help="Project id override",
        ),
    ] = None,
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Base variant id",
        ),
    ] = None,
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    store_raw: Annotated[
        bool,
        typer.Option(
            "--store-raw",
            help="Store raw HTML when ingesting a URL",
        ),
    ] = False,
    open_after: Annotated[
        bool,
        typer.Option(
            "--open",
            help="Open preview after creating the project",
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
    if bool(job_url) == bool(job_file):
        typer.echo("ERROR: Provide exactly one of --job-url or --job-file", err=True)
        raise typer.Exit(code=2)
    if json_output and open_after:
        typer.echo("ERROR: --open cannot be combined with --json", err=True)
        raise typer.Exit(code=2)

    config_path = resolve_config_path(config)
    base_variant = variant or resolve_default_variant(config_path)

    try:
        resolved_sot = resolve_sot_path(sot_path, config_path)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        if job_url:
            result = create_project_from_url(
                url=job_url,
                slug=slug,
                base_variant_id=base_variant,
                config_path=config_path,
                sot_path=resolved_sot,
                store_raw=store_raw,
            )
            job_source = job_url
        else:
            result = create_project_from_file(
                job_path=job_file or Path(),
                slug=slug,
                base_variant_id=base_variant,
                config_path=config_path,
                sot_path=resolved_sot,
                store_raw=store_raw,
            )
            job_source = str(job_file)
    except (ProjectError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    summary = _project_summary_payload(
        command="project.new",
        project_id=result.project_dir.name,
        project_dir=result.project_dir,
        base_variant=base_variant,
        job_source=job_source,
        config_path=config_path,
        proposal_variant_id=load_variant(result.variant_path).id,
    )

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(summary, indent=2, sort_keys=True))
    else:
        _print_project_new_summary(summary)

    if open_after:
        dev_serve(
            sot_path=resolved_sot,
            config=config_path,
            theme=None,
            style_preset=None,
            plain=plain,
            json_output=json_output,
            project=result.project_dir.name,
        )


def project_show(
    project: Annotated[
        str,
        typer.Argument(help="Project id or path"),
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
        summary = inspect_project(project, config=config)
    except (ProjectError, OSError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"command": "project.show", **summary}, indent=2, sort_keys=True))
        return

    _print_project_show_summary(summary)


def project_apply(
    project: Annotated[
        str,
        typer.Argument(help="Project id or path"),
    ],
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
    config_path = resolve_config_path(config)
    try:
        project_dir = resolve_project_dir(project, config_path)
        spec = load_project(project_dir)
    except ProjectError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        resolved_sot = apply_project_patch(
            project_dir=project_dir,
            sot_path=sot_path if sot_path is not None else spec.sot_path,
        )
    except ProjectError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_project_apply_summary(project_dir, resolved_sot)
