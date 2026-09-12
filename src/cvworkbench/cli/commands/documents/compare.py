"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/commands/documents/compare.py

Adapt document diff and rendered-page comparison commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from cvworkbench.cli.helpers import configure_output_mode
from cvworkbench.cli.output import OutputMode, get_output_mode, print_summary
from cvworkbench.ops.diffing import DiffError, DiffSelection, diff_artifacts, parse_artifact
from cvworkbench.ops.render_compare import RenderCompareError, compare_rendered_pdfs


def _print_diff_summary(summary: dict[str, Any]) -> None:
    side_a = summary.get("a", {})
    side_b = summary.get("b", {})
    rows: list[tuple[str, str | Path]] = [
        ("artifact_a", str(side_a.get("artifact", ""))),
        ("artifact_b", str(side_b.get("artifact", ""))),
        ("path_a", str(side_a.get("path", ""))),
        ("path_b", str(side_b.get("path", ""))),
        ("equal", str(summary.get("equal", ""))),
        ("additions", str(summary.get("additions", ""))),
        ("deletions", str(summary.get("deletions", ""))),
    ]
    print_summary("diff", rows)


def _print_compare_summary(summary: dict[str, Any]) -> None:
    run_a = summary.get("run_a", {})
    run_b = summary.get("run_b", {})
    rows: list[tuple[str, str | Path]] = [
        ("run_a", str(run_a.get("run_id", ""))),
        ("run_b", str(run_b.get("run_id", ""))),
        ("pdf_a", str(run_a.get("pdf", ""))),
        ("pdf_b", str(run_b.get("pdf", ""))),
        ("status", str(summary.get("status", ""))),
        ("page_count_a", str(summary.get("page_count_a", ""))),
        ("page_count_b", str(summary.get("page_count_b", ""))),
        ("identical_pages", str(summary.get("identical_pages", ""))),
        ("different_pages", str(summary.get("different_pages", ""))),
        ("report", str(summary.get("report", ""))),
        ("summary_json", str(summary.get("summary_json", ""))),
    ]
    print_summary("compare", rows)


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

    if get_output_mode() == OutputMode.JSON:
        payload = {"summary": summary, "diff": diff_text}
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    _print_diff_summary(summary)
    if diff_text:
        typer.echo(diff_text)


def compare(
    run_a: Annotated[
        str,
        typer.Option(
            "--run-a",
            help="Run id or path for side A",
        ),
    ],
    run_b: Annotated[
        str,
        typer.Option(
            "--run-b",
            help="Run id or path for side B",
        ),
    ],
    out_dir: Annotated[
        Path | None,
        typer.Option(
            "--out-dir",
            help="Directory to write rasterized pages and the HTML report",
        ),
    ] = None,
    dpi: Annotated[
        int,
        typer.Option(
            "--dpi",
            help="Rasterization DPI for PDF pages",
        ),
    ] = 144,
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
        result = compare_rendered_pdfs(
            config_path=config,
            run_a=run_a,
            run_b=run_b,
            out_dir=out_dir,
            dpi=dpi,
        )
    except RenderCompareError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    summary = {
        "command": "compare",
        "status": result.status,
        "run_a": {
            "run_id": result.run_a.run_id,
            "path": str(result.run_a.path),
            "pdf": str(result.pdf_a),
        },
        "run_b": {
            "run_id": result.run_b.run_id,
            "path": str(result.run_b.path),
            "pdf": str(result.pdf_b),
        },
        "page_count_a": sum(1 for page in result.pages if page.image_a is not None),
        "page_count_b": sum(1 for page in result.pages if page.image_b is not None),
        "identical_pages": sum(1 for page in result.pages if page.identical),
        "different_pages": sum(1 for page in result.pages if not page.identical),
        "out_dir": str(result.out_dir),
        "report": str(result.report_path),
        "summary_json": str(result.summary_path),
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(summary, indent=2, sort_keys=True))
        return

    _print_compare_summary(summary)
