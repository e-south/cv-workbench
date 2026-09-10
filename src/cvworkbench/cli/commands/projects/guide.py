"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/commands/projects/guide.py

Adapt job-driven project guidance and optional preview commands.

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
    _print_project_guide_summary,
    _project_summary_payload,
)
from cvworkbench.cli.helpers import configure_output_mode
from cvworkbench.cli.output import OutputMode, get_output_mode
from cvworkbench.ops.projects import (
    ProjectGuideError,
    guide_project,
)
from cvworkbench.workspace.source import (
    tags_summary_line,
    top_tags,
)


def project_guide(
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
    if (job_url is None) == (job_file is None):
        typer.echo("ERROR: Provide exactly one of --job-url or --job-file", err=True)
        raise typer.Exit(code=2)
    if json_output and open_after:
        typer.echo("ERROR: --open cannot be combined with --json", err=True)
        raise typer.Exit(code=2)

    try:
        result = guide_project(
            config_path=config,
            job_url=job_url,
            job_file=job_file,
            slug=slug,
            variant_id=variant,
            sot_path=sot_path,
            store_raw=store_raw,
        )
    except ProjectGuideError as exc:
        for error in exc.errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1) from exc

    tags_top = top_tags(result.source_tag_counts)
    summary = {
        **_project_summary_payload(
            command="project.guide",
            project_id=result.paths.project_dir.name,
            project_dir=result.paths.project_dir,
            base_variant=result.applied_variant_id,
            job_source=result.job_source,
            config_path=result.config_path,
            proposal_variant_id=result.proposal_variant_id,
        ),
        "job": result.job,
        "sot": {
            "path": str(result.sot_path),
            "tags_top": tags_top,
            "tags_summary": tags_summary_line(tags_top),
        },
        "variants": {
            "config": result.variant_catalog,
            "count": len(result.variant_catalog),
            "default": result.default_variant_id,
        },
        "recommendations": result.recommendations,
        "proposal_plan": result.proposal_plan,
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(summary, indent=2, sort_keys=True))
    else:
        _print_project_guide_summary(summary)

    if open_after:
        dev_serve(
            sot_path=result.sot_path,
            config=result.config_path,
            theme=None,
            style_preset=None,
            plain=plain,
            json_output=json_output,
            project=result.paths.project_dir.name,
        )
