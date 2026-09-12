"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/commands/documents/review.py

Adapt selection explanation, content-review packaging, and DOCX import commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from cvworkbench.build.explain import ExplainError, explain_item, load_selection
from cvworkbench.cli.helpers import configure_output_mode, resolve_selection_path
from cvworkbench.cli.output import OutputMode, get_output_mode, print_summary
from cvworkbench.config import (
    resolve_config_path,
    resolve_default_variant,
)
from cvworkbench.ops.projects import (
    ProjectError,
    resolve_project_dir,
)
from cvworkbench.ops.review import ReviewError
from cvworkbench.ops.review.importing import import_docx_review
from cvworkbench.ops.review.packs import build_review_pack
from cvworkbench.ops.review.record import SOURCE_RECORD_NAME
from cvworkbench.workspace.commands import shell_command


def _print_explain_summary(item: dict[str, Any]) -> None:
    reasons = item.get("reasons") or []
    tags = item.get("tags") or []
    rows: list[tuple[str, str | Path]] = [
        ("id", str(item.get("id", ""))),
        ("type", str(item.get("type", ""))),
        ("included", str(item.get("included", ""))),
        ("reasons", ", ".join(reasons)),
        ("tags", ", ".join(tags)),
    ]
    if "text" in item and item.get("text"):
        rows.append(("text", str(item.get("text"))))
    if "label" in item and item.get("label"):
        rows.append(("label", str(item.get("label"))))
    if "role_id" in item:
        rows.append(("role_id", str(item.get("role_id"))))
    if "letter_id" in item:
        rows.append(("letter_id", str(item.get("letter_id"))))
    if "section" in item:
        rows.append(("section", str(item.get("section"))))
    print_summary("explain", rows)


def _print_reviewpack_summary(summary: dict[str, str | Path]) -> None:
    rows = [(key, value) for key, value in summary.items()]
    print_summary("reviewpack", rows)


def _print_import_summary(summary: dict[str, str | Path]) -> None:
    rows = [(key, value) for key, value in summary.items()]
    print_summary("import-docx", rows)


def _reviewpack_error_hint(
    *,
    message: str,
    project: str | None,
    run: str | None,
    variant_id: str | None,
) -> str:
    if message.startswith("Run does not belong to project:"):
        project_label = project or "<project-id>"
        selector_hint = shell_command(f"reviewpack --project {project_label}")
        return (
            f"HINT: the selected run does not belong to project {project_label!r}. "
            f"Use `{selector_hint}` to package that project's latest run, pass a "
            "matching `--run projects/<project-id>/<run-id>`, or drop `--project` "
            "if you intended to package the selected run directly."
        )
    if message.startswith("Review pack already exists:"):
        if run is not None:
            force_hint = shell_command(f"reviewpack --run {run} --force")
        elif project is not None:
            force_hint = shell_command(f"reviewpack --project {project} --force")
        else:
            force_hint = shell_command(f"reviewpack --variant {variant_id or '<variant>'} --force")
        return f"HINT: use `{force_hint}` to replace the existing review pack explicitly."

    build_hint = (
        f"build --project {project!r} --format md,pdf,docx"
        if project is not None
        else f"build --variant {variant_id or '<variant>'} --format md,pdf,docx"
    )
    return (
        "HINT: build the target variant with review artifacts first, for example "
        f"`{shell_command(build_hint)}`, "
        f"inspect `{shell_command('workflow --id review.import')}`, "
        "pass `--run <run-id>` to package a specific build deterministically, "
        "or use `--force` to replace an existing review pack."
    )


def explain(
    item_id: Annotated[
        str,
        typer.Option(
            "--id",
            help="Selection item id to explain",
        ),
    ],
    selection: Annotated[
        Path | None,
        typer.Option(
            "--selection",
            help="Path to selection.json",
        ),
    ] = None,
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id for dist selection lookup",
        ),
    ] = None,
    run: Annotated[
        str | None,
        typer.Option(
            "--run",
            help="Run id or path for selection lookup",
        ),
    ] = None,
    item_type: Annotated[
        str | None,
        typer.Option(
            "--type",
            help="Item type filter (bullet or section)",
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
    selection_path = resolve_selection_path(selection, config, variant, run)
    try:
        payload = load_selection(selection_path)
        explained = explain_item(payload, item_id, item_type)
    except ExplainError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(explained.item, indent=2, sort_keys=True))
        return

    _print_explain_summary(explained.item)


def reviewpack(
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id to package for review; cannot be combined with --run or --project",
        ),
    ] = None,
    run: Annotated[
        str | None,
        typer.Option(
            "--run",
            help="Run id or path to package deterministically",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path to package from its latest run; cannot be combined with --variant",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Replace an existing review pack directory explicitly",
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
    if run and variant:
        typer.echo("ERROR: --run cannot be combined with --variant", err=True)
        raise typer.Exit(code=2)
    if project and variant:
        typer.echo("ERROR: --project cannot be combined with --variant", err=True)
        raise typer.Exit(code=2)
    config_path = resolve_config_path(config)
    project_dir = None
    if project is not None:
        try:
            project_dir = resolve_project_dir(project, config_path)
        except ProjectError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    resolved_variant = (
        variant if (run or project_dir) else (variant or resolve_default_variant(config_path))
    )
    try:
        pack = build_review_pack(
            variant_id=resolved_variant,
            config_path=config_path,
            run=run,
            project_dir=project_dir,
            force=force,
        )
    except ReviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        typer.echo(
            _reviewpack_error_hint(
                message=str(exc),
                project=project,
                run=run,
                variant_id=resolved_variant,
            ),
            err=True,
        )
        raise typer.Exit(code=1) from exc

    summary = {
        "out_dir": pack.out_dir,
        "docx": pack.docx_path,
        "pdf": pack.pdf_path,
        "review": pack.review_path,
        "run_id": pack.run_id,
        "source_record": pack.source_record_path,
    }
    _print_reviewpack_summary(summary)


def import_docx(
    docx_path: Annotated[
        Path,
        typer.Option(
            "--from",
            help="Path to a DOCX file to import",
        ),
    ],
    run: Annotated[
        str | None,
        typer.Option(
            "--run",
            help="Run id or path to locate canonical markdown; combine with --project to pin a project run",
        ),
    ] = None,
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Require the recorded source variant; cannot be combined with --run or --project",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Require the source project; without a review record also provide --run",
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
    if run and variant:
        typer.echo("ERROR: --run cannot be combined with --variant", err=True)
        raise typer.Exit(code=2)
    if project and variant:
        typer.echo("ERROR: --project cannot be combined with --variant", err=True)
        raise typer.Exit(code=2)
    if (
        not run
        and not variant
        and not project
        and not (docx_path.parent / SOURCE_RECORD_NAME).exists()
    ):
        typer.echo("ERROR: Provide one of --run, --variant, or --project", err=True)
        raise typer.Exit(code=2)
    config_path = resolve_config_path(config)
    project_dir = None
    if project is not None:
        try:
            project_dir = resolve_project_dir(project, config_path)
        except ProjectError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    try:
        result = import_docx_review(
            docx_path=docx_path,
            config_path=config_path,
            run=run,
            variant_id=variant,
            project_dir=project_dir,
        )
    except ReviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        typer.echo(
            (
                f"HINT: run `{shell_command('reviewpack --variant <variant>')}` or "
                f"`{shell_command('reviewpack --project <project-id>')}` after building review "
                "artifacts, or pass `--run <run-id>` when importing against a specific canonical output."
            ),
            err=True,
        )
        raise typer.Exit(code=1) from exc

    summary = {
        "draft_dir": result.draft_dir,
        "patch": result.patch_path,
        "metadata": result.metadata_path,
        "notes": result.notes_path,
        "imported_markdown": result.imported_path,
        "run_id": result.run_id,
        "apply_status": result.apply_status,
        "next_step": (
            f"Review notes.md, then apply {result.patch_path.name} after explicit approval if draft.json reports ready"
            if result.apply_status == "ready"
            else "Review notes.md; draft.json records a verified no-op"
            if result.apply_status == "ready_no_changes"
            else "Review notes.md and author a real SoT patch manually; draft.json records review_diff_only"
        ),
    }
    _print_import_summary(summary)
