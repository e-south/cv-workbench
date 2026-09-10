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
    inspect_guidance_inputs,
    load_project,
    load_project_details,
    load_project_plan,
    project_patch_render_warning,
    project_patch_status,
    resolve_project_dir,
)
from cvworkbench.variants import load_variant
from cvworkbench.workspace.project_guidance import (
    guidance_input_context,
    project_artifact_context,
    proposal_plan_selection_warning,
)
from cvworkbench.workspace.projects import (
    project_commands,
    project_review_payload,
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
        _print_project_new_summary(
            project_dir=result.project_dir,
            variant_id=load_variant(result.variant_path).id,
            job_source=job_source,
        )

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
    config_path = resolve_config_path(config)
    project_dir = resolve_project_dir(project, config_path)
    try:
        details = load_project_details(project_dir)
    except ProjectError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    review = project_review_payload(details.spec.project_id, config_path)
    commands = project_commands(
        details.spec.project_id,
        config_path=config_path,
        variant_id=details.proposal_variant_id,
        review_run_id=review["run_id"] if review["review_ready"] else None,
    )
    review["next_command"] = commands.get("reviewpack", commands["build"])
    render_warning = project_patch_render_warning(
        proposal_document_type=details.proposal_document_type,
        patch_operations=details.patch_operations,
    )
    patch_status = project_patch_status(
        patch_format=details.patch_format,
        patch_is_empty=details.patch_is_empty,
        patch_line_count=details.patch_line_count,
    )
    proposal_plan, proposal_plan_error = load_project_plan(details)
    summary = {
        "project": {
            "project_id": details.spec.project_id,
            "project_dir": str(details.spec.project_dir),
            "created_at": details.created_at,
            "base_variant": details.spec.base_variant_id,
            "sot_path": str(details.spec.sot_path),
        },
        "proposal": {
            "variant_id": details.proposal_variant_id,
            "variant_path": str(details.spec.variant_path),
            "document_type": details.proposal_document_type,
        },
        "job": {
            "source_type": details.job_source_type,
            "source": details.job_source_value,
            "extracted_path": str(details.extracted_path),
            "raw_path": str(details.raw_path) if details.raw_path is not None else None,
        },
        "signals": {
            "path": str(details.signals_path),
        },
        "patch": {
            "path": str(details.spec.patch_path),
            "format": details.patch_format,
            "is_empty": details.patch_is_empty,
            "line_count": details.patch_line_count,
            "operations": list(details.patch_operations),
            "render_warning": render_warning,
            "status": patch_status,
        },
        "review": review,
        "commands": commands,
        **project_artifact_context(details.artifact_checks, include_details=True),
    }
    if proposal_plan is not None:
        summary["proposal_plan"] = proposal_plan
        summary.update(
            guidance_input_context(
                inspect_guidance_inputs(proposal_plan, details=details, config_path=config_path)
            )
        )
    if proposal_plan_error is not None:
        summary["proposal_plan_error"] = proposal_plan_error
    plan_warning = proposal_plan_selection_warning(proposal_plan, details.spec.base_variant_id)
    if plan_warning is not None:
        summary["proposal_plan_warning"] = plan_warning

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
    project_dir = resolve_project_dir(project, config_path)
    try:
        spec = load_project(project_dir)
    except ProjectError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    resolved_sot = spec.sot_path
    if sot_path is not None:
        try:
            resolved_sot = resolve_sot_path(sot_path, config_path)
        except (FileNotFoundError, ValueError) as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    try:
        apply_project_patch(project_dir=project_dir, sot_path=resolved_sot)
    except ProjectError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_project_apply_summary(project_dir, resolved_sot)
