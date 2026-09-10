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
from cvworkbench.cli.helpers import _validate_sot, configure_output_mode
from cvworkbench.cli.output import OutputMode, get_output_mode
from cvworkbench.config import (
    resolve_config_path,
    resolve_default_variant,
    resolve_sot_path,
)
from cvworkbench.inputs.sot import load_sot
from cvworkbench.inputs.tags import extract_tags, tag_counts
from cvworkbench.ops.projects import (
    ProjectError,
    create_project_from_file,
    create_project_from_url,
    discard_project_workspace,
    retarget_project_variant,
)
from cvworkbench.variants import load_variant
from cvworkbench.workspace.project_guidance import (
    build_job_evidence,
    build_proposal_plan,
    job_keyword_overlap,
    job_signal_counts,
    load_job_signals,
    normalize_keywords,
    recommend_variants,
)
from cvworkbench.workspace.source import (
    tags_summary_line,
    top_tags,
)
from cvworkbench.workspace.variants import (
    load_variants_from_config,
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
    if bool(job_url) == bool(job_file):
        typer.echo("ERROR: Provide exactly one of --job-url or --job-file", err=True)
        raise typer.Exit(code=2)
    if json_output and open_after:
        typer.echo("ERROR: --open cannot be combined with --json", err=True)
        raise typer.Exit(code=2)

    config_path = resolve_config_path(config)
    try:
        configured_default_variant = resolve_default_variant(config_path)
        requested_variant = variant or configured_default_variant
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        resolved_sot = resolve_sot_path(sot_path, config_path)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    errors = _validate_sot(resolved_sot)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)
    try:
        sot_payload = load_sot(resolved_sot)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    tags = extract_tags(sot_payload)
    counts = tag_counts(tags)
    tags_top = top_tags(counts)
    tags_summary = tags_summary_line(tags_top)

    try:
        if job_url:
            project_paths = create_project_from_url(
                url=job_url,
                slug=slug,
                base_variant_id=requested_variant,
                config_path=config_path,
                sot_path=resolved_sot,
                store_raw=store_raw,
            )
            job_source = job_url
        else:
            project_paths = create_project_from_file(
                job_path=job_file or Path(),
                slug=slug,
                base_variant_id=requested_variant,
                config_path=config_path,
                sot_path=resolved_sot,
                store_raw=store_raw,
            )
            job_source = str(job_file)
    except (ProjectError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        signals = load_job_signals(project_paths.signals_path)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    raw_keywords: list[str] = []
    keywords_value = signals.get("keywords")
    if isinstance(keywords_value, list):
        raw_keywords = [item for item in keywords_value if isinstance(item, str)]
    job_keywords = normalize_keywords(raw_keywords)
    keyword_overlap = job_keyword_overlap(job_keywords, counts)
    signal_counts = job_signal_counts(signals, job_keywords)
    job_text = project_paths.extracted_path.read_text()
    job_evidence = build_job_evidence(
        job_text,
        signals=signals,
        job_keywords=job_keywords,
    )

    try:
        variants = load_variants_from_config(config_path)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    recommendations = recommend_variants(
        variants,
        job_keywords,
        counts,
        configured_default_variant,
        signal_counts,
    )
    applied_variant = requested_variant
    selection_mode = "explicit" if variant else "requested"
    selected_recommendation = recommendations[0] if recommendations else None
    if (
        variant is None
        and selected_recommendation is not None
        and selected_recommendation["eligible"]
    ):
        recommended_variant = selected_recommendation["variant_id"]
        if recommended_variant != requested_variant:
            try:
                retarget_project_variant(
                    project_dir=project_paths.project_dir,
                    base_variant_id=recommended_variant,
                    config_path=config_path,
                )
            except Exception as exc:
                try:
                    discard_project_workspace(
                        project_dir=project_paths.project_dir,
                        config_path=config_path,
                    )
                except Exception as rollback_exc:
                    typer.echo(f"ERROR: {exc}", err=True)
                    typer.echo(
                        "ERROR: Failed to roll back the project workspace after guide retargeting failed: "
                        f"{rollback_exc}",
                        err=True,
                    )
                    raise typer.Exit(code=1) from exc
                typer.echo(f"ERROR: {exc}", err=True)
                raise typer.Exit(code=1) from exc
        applied_variant = recommended_variant
        selection_mode = "recommended"
    proposal_plan = build_proposal_plan(
        project_id=project_paths.project_dir.name,
        project_dir=project_paths.project_dir,
        job_keywords=job_keywords,
        keyword_overlap=keyword_overlap,
        recommendations=recommendations,
        job_evidence=job_evidence,
        requested_variant=requested_variant,
        applied_variant=applied_variant,
        selection_mode=selection_mode,
    )
    proposal_plan_path = Path(proposal_plan["path"])
    proposal_plan_path.write_text(json.dumps(proposal_plan, indent=2, sort_keys=True) + "\n")

    summary = {
        **_project_summary_payload(
            command="project.guide",
            project_id=project_paths.project_dir.name,
            project_dir=project_paths.project_dir,
            base_variant=applied_variant,
            job_source=job_source,
            config_path=config_path,
            proposal_variant_id=load_variant(project_paths.variant_path).id,
        ),
        "job": {
            "keywords": job_keywords,
            "keywords_in_sot": keyword_overlap["matched"],
            "keywords_missing": keyword_overlap["missing"],
            "evidence": job_evidence,
        },
        "sot": {
            "path": str(resolved_sot),
            "tags_top": tags_top,
            "tags_summary": tags_summary,
        },
        "variants": {
            "config": variants,
            "count": len(variants),
            "default": configured_default_variant,
        },
        "recommendations": recommendations,
        "proposal_plan": proposal_plan,
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(summary, indent=2, sort_keys=True))
    else:
        _print_project_guide_summary(summary)

    if open_after:
        dev_serve(
            sot_path=resolved_sot,
            config=config_path,
            theme=None,
            style_preset=None,
            plain=plain,
            json_output=json_output,
            project=project_paths.project_dir.name,
        )
