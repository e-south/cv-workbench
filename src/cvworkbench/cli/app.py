"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/app.py

Command-line interface for the CV workbench.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from cvworkbench.cli.helpers import configure_output_mode, load_sot_payload, resolve_selection_path
from cvworkbench.cli.output import OutputMode, get_output_mode, print_summary
from cvworkbench.config import (
    resolve_config_path,
    resolve_default_variant,
    resolve_default_theme,
    resolve_drafts_path,
    resolve_dist_path,
    resolve_pdf_engine,
    resolve_project_path,
    resolve_runs_path,
    resolve_sot_path,
    resolve_style_preset,
    resolve_sync_mode,
    resolve_themes_dir,
    resolve_variant_path,
)
from cvworkbench.build.explain import ExplainError, explain_item, load_selection
from cvworkbench.build.paths import filters_dir, output_path
from cvworkbench.build.pipeline import BuildResult, build_documents
from cvworkbench.build.rendering import RenderError, render_document
from cvworkbench.build.styles import prepare_html_style
from cvworkbench.dev.preview import PreviewController, PreviewError, serve_preview
from cvworkbench.ingestion.registry import RegistryError, add_url_context
from cvworkbench.inputs.tags import extract_tags, lint_tags, tag_counts
from cvworkbench.inputs.validation import validate_sot
from cvworkbench.inputs.sot_versions import SotVersionError, resolve_versioned_root
from cvworkbench.ops.apply import ApplyError, apply_draft
from cvworkbench.ops.clean import CleanError, clean_path
from cvworkbench.ops.diffing import DiffError, DiffSelection, diff_artifacts, parse_artifact
from cvworkbench.ops.doctor import run_doctor
from cvworkbench.ops.review import ReviewError, build_review_pack, import_docx_review
from cvworkbench.ops.scaffold import ScaffoldError, init_project, resolve_template_root
from cvworkbench.ops.sot_versions import (
    SotPackError,
    activate_version,
    create_version,
    diff_versions,
    list_versions,
)
from cvworkbench.ops.syncing import SyncError, SyncResult, sync_site
from cvworkbench.ops.tailor import DraftPaths, TailorError, tailor_job
from cvworkbench.ops.variant_promote import PromoteError, promote_variant
from cvworkbench.themes import ThemeError, build_render_plan, list_themes, resolve_theme
from cvworkbench.variants import load_variant

app = typer.Typer(add_completion=False, no_args_is_help=True)
job_app = typer.Typer(no_args_is_help=True)
tags_app = typer.Typer(no_args_is_help=True)
theme_app = typer.Typer(no_args_is_help=True)
dev_app = typer.Typer(no_args_is_help=True)
variant_app = typer.Typer(no_args_is_help=True)
clean_app = typer.Typer(no_args_is_help=True)
sot_app = typer.Typer(no_args_is_help=True)
app.add_typer(job_app, name="job")
app.add_typer(tags_app, name="tags")
app.add_typer(theme_app, name="theme")
app.add_typer(dev_app, name="dev")
app.add_typer(variant_app, name="variant")
app.add_typer(clean_app, name="clean")
app.add_typer(sot_app, name="sot")


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


def _print_sync_summary(result: SyncResult) -> None:
    plan = result.plan
    changed_files = len(plan.copy_ops)
    if plan.frontmatter_content:
        changed_files += 1
    status = "no_changes"
    if plan.has_changes():
        status = "pr_created" if result.mode == "pr" else "applied"

    rows: list[tuple[str, str | Path]] = [
        ("sync_mode", result.mode),
        ("sync_status", status),
        ("site_repo", result.site.repo_path),
        ("pdf_url", plan.pdf_url),
        ("files_updated", str(changed_files)),
    ]
    if result.branch:
        rows.append(("branch", result.branch))
    print_summary("sync", rows)


def _print_validate_summary(sot_path: Path) -> None:
    print_summary(
        "validate",
        [
            ("status", "ok"),
            ("sot_path", sot_path),
        ],
    )


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


def _print_doctor_summary(rows: list[tuple[str, str | Path]]) -> None:
    print_summary("doctor", rows)


def _print_init_summary(result: dict[str, str | Path]) -> None:
    rows = [(key, value) for key, value in result.items()]
    print_summary("init", rows)


def _print_job_add_summary(entry: dict[str, str | Path]) -> None:
    rows = [(key, value) for key, value in entry.items()]
    print_summary("job.add", rows)


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
    if "section" in item:
        rows.append(("section", str(item.get("section"))))
    print_summary("explain", rows)


def _print_reviewpack_summary(summary: dict[str, str | Path]) -> None:
    rows = [(key, value) for key, value in summary.items()]
    print_summary("reviewpack", rows)


def _print_import_summary(summary: dict[str, str | Path]) -> None:
    rows = [(key, value) for key, value in summary.items()]
    print_summary("import-docx", rows)


def _print_variant_promote_summary(variant_id: str, variant_path: Path, status: str) -> None:
    print_summary(
        "variant.promote",
        [
            ("variant_id", variant_id),
            ("variant_path", variant_path),
            ("status", status),
        ],
    )


def _print_clean_summary(target: str, path: Path, removed: int, status: str) -> None:
    print_summary(
        "clean",
        [
            ("target", target),
            ("path", path),
            ("removed", str(removed)),
            ("status", status),
        ],
    )


def _print_theme_list_summary(theme_ids: list[str], default_theme: str) -> None:
    print_summary(
        "theme.list",
        [
            ("themes", ", ".join(theme_ids)),
            ("default", default_theme),
        ],
    )


def _print_theme_info_summary(theme_id: str, description: str | None, routes: list[str]) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("id", theme_id),
        ("routes", ", ".join(routes)),
    ]
    if description:
        rows.append(("description", description))
    print_summary("theme.info", rows)


def _print_serve_summary(
    output_path: Path,
    preview_url: str,
    opened: bool,
    watching: bool,
) -> None:
    print_summary(
        "serve",
        [
            ("output_html", output_path),
            ("preview_url", preview_url),
            ("opened_browser", str(opened).lower()),
            ("watching", str(watching).lower()),
            ("controls", "t=theme p=preset r=rebuild"),
        ],
    )


def _open_in_browser(path: str | Path) -> tuple[bool, str | None]:
    if os.environ.get("CVW_SKIP_OPEN") == "1":
        return False, None
    target = str(path)

    try:
        if sys.platform == "darwin":
            return _run_open_command(["/usr/bin/open", target])
        if os.name == "nt":
            os.startfile(target)
            return True, None
        return _run_open_command(["xdg-open", target])
    except FileNotFoundError as exc:
        return False, f"Browser opener not found: {exc.filename}"
    except OSError as exc:
        return False, str(exc)


def _run_open_command(args: list[str]) -> tuple[bool, str | None]:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        return False, message or "Browser open failed"
    return True, None


def _resolve_sot_root(sot_path: Path | None, config: Path) -> Path:
    try:
        resolved = resolve_sot_path(sot_path, config)
        return resolve_versioned_root(resolved)
    except (FileNotFoundError, ValueError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _print_quickstart_summary(result: BuildResult, sample_sot: Path) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("sample_sot", sample_sot),
        ("variant", result.variant.id),
        ("outputs_dir", result.dist_dir),
        ("run_dir", result.run_dir),
        ("manifest_dist", result.dist_dir / "manifest.json"),
        ("manifest_run", result.run_dir / "manifest.json"),
    ]
    if result.theme_id:
        rows.append(("theme", result.theme_id))
    if result.style_preset:
        rows.append(("style_preset", result.style_preset))
    rows.append(("next_step", "cvw dev serve --sot-path ./sot.sample --variant base"))
    for fmt in result.formats:
        rows.append((f"output_{fmt}", output_path(result.dist_dir, result.variant, fmt)))
    print_summary("quickstart", rows)


def _print_tailor_summary(paths: DraftPaths, output_dir: Path, base_variant: str) -> None:
    print_summary(
        "tailor",
        [
            ("draft_dir", output_dir),
            ("base_variant", base_variant),
            ("variant", paths.variant_path),
            ("patch", paths.patch_path),
            ("job", paths.job_path),
            ("prompt", paths.prompt_path),
        ],
    )


def _print_apply_summary(draft_dir: Path, patch_path: Path, status: str, sot_path: Path) -> None:
    print_summary(
        "apply",
        [
            ("draft_dir", draft_dir),
            ("patch", patch_path),
            ("status", status),
            ("sot_path", sot_path),
        ],
    )


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
        resolved = resolve_sot_path(sot_path, config)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    errors = validate_sot(resolved)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)
    _print_validate_summary(resolved)


@app.command()
def doctor(
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
        checks = run_doctor(config)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    rows: list[tuple[str, str | Path]] = []
    missing: list[str] = []
    for check in checks:
        status = "ok" if check.ok else "missing"
        detail = status
        if check.version:
            detail = f"{status} ({check.version})"
        elif check.message:
            detail = f"{status} ({check.message})"
        rows.append((check.name, detail))
        if not check.ok:
            missing.append(check.name)

    _print_doctor_summary(rows)
    if missing:
        typer.echo(
            f"ERROR: Missing dependencies: {', '.join(missing)}",
            err=True,
        )
        raise typer.Exit(code=1)


@app.command()
def init(
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
        result = init_project(Path.cwd())
    except ScaffoldError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    statuses = result.statuses
    summary = {
        "root": result.root,
        "sot_path": result.sot_path,
        "sot_status": statuses.get("sot", "unknown"),
        "workbench_config": result.config_path,
        "workbench_status": statuses.get("workbench_config", "unknown"),
        "base_variant": result.variant_path,
        "base_variant_status": statuses.get("base_variant", "unknown"),
        "publish_config": result.config_path.parent / "publish.yaml",
        "publish_status": statuses.get("publish_config", "unknown"),
        "themes_path": result.root / "build" / "themes",
        "themes_status": statuses.get("themes", "unknown"),
        "registry_path": result.registry_path,
        "registry_status": statuses.get("registry", "unknown"),
    }
    _print_init_summary(summary)


@app.command()
def quickstart(
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
        init_project(Path.cwd())
    except ScaffoldError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    template_root = resolve_template_root()
    sample_sot = template_root / "sot.sample"
    if not sample_sot.exists():
        typer.echo(f"ERROR: Sample SoT not found: {sample_sot}", err=True)
        raise typer.Exit(code=1)

    errors = validate_sot(sample_sot)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)

    try:
        result = build_documents(
            sot_path=sample_sot,
            config_path=config,
            variant_id="base",
            formats=["md", "pdf", "docx"],
        )
    except (ValueError, RenderError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_quickstart_summary(result, sample_sot)


@theme_app.command("list")
def theme_list(
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
        themes_dir = resolve_themes_dir(config)
        default_theme = resolve_default_theme(config)
        themes = list_themes(themes_dir)
    except (ValueError, ThemeError, FileNotFoundError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    theme_ids = [theme.id for theme in themes]
    _print_theme_list_summary(theme_ids, default_theme)


@theme_app.command("info")
def theme_info(
    theme: Annotated[
        str,
        typer.Argument(help="Theme id"),
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
        themes_dir = resolve_themes_dir(config)
        resolved = resolve_theme(themes_dir, theme)
    except (ValueError, ThemeError, FileNotFoundError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    routes = list(resolved.routes.keys())
    _print_theme_info_summary(resolved.id, resolved.description, routes)


@variant_app.command("promote")
def variant_promote(
    draft: Annotated[
        Path,
        typer.Option(
            "--draft",
            help="Draft directory containing variant.yaml",
        ),
    ],
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    variant_id: Annotated[
        str | None,
        typer.Option(
            "--id",
            help="Override the promoted variant id",
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
        result = promote_variant(
            draft_dir=draft,
            config_path=config,
            variant_id=variant_id,
        )
    except (PromoteError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_variant_promote_summary(result.variant_id, result.variant_path, result.status)


@clean_app.command("runs")
def clean_runs(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of all run artifacts",
        ),
    ] = False,
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
        path = resolve_runs_path(config)
        result = clean_path(target="runs", path=path, confirm=yes)
    except (CleanError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_clean_summary(result.target, result.path, result.removed, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


@clean_app.command("dist")
def clean_dist(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of all dist artifacts",
        ),
    ] = False,
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
        path = resolve_dist_path(config)
        result = clean_path(target="dist", path=path, confirm=yes)
    except (CleanError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_clean_summary(result.target, result.path, result.removed, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


@clean_app.command("drafts")
def clean_drafts(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of all draft artifacts",
        ),
    ] = False,
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
        path = resolve_drafts_path(config)
        result = clean_path(target="drafts", path=path, confirm=yes)
    except (CleanError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_clean_summary(result.target, result.path, result.removed, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


@sot_app.command("list")
def sot_list(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the SoT version pack root",
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
    root = _resolve_sot_root(sot_path, config)
    try:
        state = list_versions(root)
    except (SotPackError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    print_summary(
        "sot.list",
        [
            ("root", state.root),
            ("active", state.active),
            ("versions", ", ".join(state.versions)),
        ],
    )


@sot_app.command("new")
def sot_new(
    name: Annotated[
        str,
        typer.Argument(help="Name for the new SoT version"),
    ],
    from_version: Annotated[
        str | None,
        typer.Option(
            "--from",
            help="Base SoT version to copy from",
        ),
    ] = None,
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the SoT version pack root",
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
    root = _resolve_sot_root(sot_path, config)
    try:
        state = list_versions(root)
        base = from_version or state.active
        target = create_version(root, name, base)
    except (SotPackError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    print_summary(
        "sot.new",
        [
            ("name", name),
            ("from", base),
            ("path", target),
        ],
    )


@sot_app.command("activate")
def sot_activate(
    name: Annotated[
        str,
        typer.Argument(help="SoT version to activate"),
    ],
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the SoT version pack root",
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
    root = _resolve_sot_root(sot_path, config)
    try:
        activate_version(root, name)
    except (SotPackError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    print_summary(
        "sot.activate",
        [
            ("root", root),
            ("active", name),
        ],
    )


@sot_app.command("diff")
def sot_diff(
    left: Annotated[
        str,
        typer.Argument(help="Left-hand SoT version"),
    ],
    right: Annotated[
        str,
        typer.Argument(help="Right-hand SoT version"),
    ],
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the SoT version pack root",
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
    root = _resolve_sot_root(sot_path, config)
    try:
        diff_text = diff_versions(root, left, right)
    except (SotPackError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if diff_text:
        typer.echo(diff_text)
        return
    typer.echo("No differences found.")


@job_app.command("add")
def job_add(
    url: Annotated[
        str,
        typer.Option(
            "--url",
            help="URL to ingest as a context source",
        ),
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
        entry = add_url_context(url, config)
    except (FileNotFoundError, ValueError, RegistryError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    summary = {
        "context_id": entry.context_id,
        "context_path": entry.path,
        "source": entry.source_path,
        "extracted": entry.extracted_path,
        "signals": entry.signals_path,
        "strategy": entry.strategy_path,
    }
    _print_job_add_summary(summary)


@tags_app.command("list")
def tags_list(
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
    payload = load_sot_payload(sot_path, config)
    tags = extract_tags(payload)
    values = sorted({info.normalized for info in tags if info.normalized})

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"tags": values}, indent=2, sort_keys=True))
        return

    for tag in values:
        typer.echo(tag)


@tags_app.command("stats")
def tags_stats(
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
    payload = load_sot_payload(sot_path, config)
    tags = extract_tags(payload)
    counts = tag_counts(tags)

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"counts": counts}, indent=2, sort_keys=True))
        return

    for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        typer.echo(f"{tag}: {count}")


@tags_app.command("lint")
def tags_lint(
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
    payload = load_sot_payload(sot_path, config)
    tags = extract_tags(payload)
    issues = lint_tags(tags)

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"issues": issues}, indent=2, sort_keys=True))
    else:
        if issues:
            for issue in issues:
                typer.echo(issue)
        else:
            typer.echo("ok")

    if issues:
        raise typer.Exit(code=1)


@app.command()
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


@app.command()
def reviewpack(
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id to package for review",
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
    resolved_variant = variant or resolve_default_variant(config)
    try:
        pack = build_review_pack(
            variant_id=resolved_variant,
            config_path=config,
        )
    except ReviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    summary = {
        "out_dir": pack.out_dir,
        "docx": pack.docx_path,
        "pdf": pack.pdf_path,
        "review": pack.review_path,
    }
    _print_reviewpack_summary(summary)


@app.command("import-docx")
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
            help="Run id or path to locate canonical markdown",
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
    try:
        result = import_docx_review(
            docx_path=docx_path,
            config_path=config,
            run=run,
        )
    except ReviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    summary = {
        "draft_dir": result.draft_dir,
        "patch": result.patch_path,
        "notes": result.notes_path,
        "imported_markdown": result.imported_path,
    }
    _print_import_summary(summary)


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
            theme=theme,
            style_preset=style_preset,
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
        resolved_variant = variant or resolve_default_variant(config)
        variant_path = resolve_variant_path(resolved_variant, config)
        resolved = load_variant(variant_path)
        dist_dir = resolve_dist_path(config) / resolved.id
        dist_dir.mkdir(parents=True, exist_ok=True)
        pdf_engine = resolve_pdf_engine(config)
        theme_id = theme or resolved.render_theme or resolve_default_theme(config)
        preset = style_preset or resolved.render_style_preset or resolve_style_preset(config)
        theme_dir = resolve_themes_dir(config)
        theme_obj = resolve_theme(theme_dir, theme_id)
    except (FileNotFoundError, ValueError, ThemeError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    parsed_formats = _parse_formats(formats) or resolved.outputs
    filters_path = filters_dir()
    output_files: dict[str, Path] = {}
    for fmt in parsed_formats:
        output_file = output_path(dist_dir, resolved, fmt)
        try:
            plan = build_render_plan(
                output_format=fmt,
                theme=theme_obj,
                style_preset=preset,
                pdf_engine=pdf_engine,
            )
            if fmt == "html":
                plan = prepare_html_style(dist_dir, plan, theme_obj.id, preset)
            render_document(
                canonical,
                output_file,
                resolved,
                filters_path,
                fmt,
                pdf_engine,
                plan,
            )
        except RenderError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        output_files[fmt] = output_file
    _print_render_summary(canonical, resolved.id, dist_dir, output_files)


@dev_app.command("serve")
def dev_serve(
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
            help="Variant id to build for preview",
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
    config_path = resolve_config_path(config)
    try:
        resolved = resolve_sot_path(sot_path, config_path)
    except (FileNotFoundError, ValueError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        resolved_variant = variant or resolve_default_variant(config_path)
        variant_path = resolve_variant_path(resolved_variant, config_path)
        resolved_variant_obj = load_variant(variant_path)
        resolved_theme = theme or resolved_variant_obj.render_theme or resolve_default_theme(config_path)
        resolved_preset = (
            style_preset
            or resolved_variant_obj.render_style_preset
            or resolve_style_preset(config_path)
        )
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        sot_base = resolve_versioned_root(resolved)
    except SotVersionError:
        sot_base = resolved

    controller = PreviewController(
        sot_base=sot_base,
        config_path=config_path,
        variant_id=resolved_variant,
        theme_id=resolved_theme,
        style_preset=resolved_preset,
    )
    host = os.environ.get("CVW_DEV_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("CVW_DEV_PORT", "8765"))
    except ValueError as exc:
        typer.echo("ERROR: CVW_DEV_PORT must be an integer", err=True)
        raise typer.Exit(code=1) from exc
    preview_url = f"http://{host}:{port}/"

    if os.environ.get("CVW_DEV_ONCE") == "1":
        try:
            state = controller.build_once()
        except PreviewError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        opened, error = _open_in_browser(state.html_path)
        if error:
            typer.echo(f"WARN: {error}", err=True)
        _print_serve_summary(state.html_path, str(state.html_path), opened, False)
        return

    def _on_start(url: str, html_path: Path) -> None:
        opened, error = _open_in_browser(url)
        if error:
            typer.echo(f"WARN: {error}", err=True)
        _print_serve_summary(html_path, url, opened, True)

    try:
        serve_preview(controller=controller, host=host, port=port, on_start=_on_start)
    except PreviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except OSError as exc:
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
        resolved_out = resolve_project_path(out, config)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    try:
        paths = tailor_job(
            job_path=job,
            base_variant_id=base_variant,
            output_dir=resolved_out,
            config_path=config,
        )
    except TailorError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_tailor_summary(paths, resolved_out, base_variant)


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
        patch_path = draft / "patch.diff"
        patch_empty = patch_path.exists() and not patch_path.read_text().strip()
        apply_draft(draft_dir=draft, sot_path=sot_path)
    except ApplyError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    status = "no_changes" if patch_empty else "applied"
    _print_apply_summary(draft, patch_path, status, sot_path)


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


@app.command()
def sync(
    mode: Annotated[
        str | None,
        typer.Option(
            "--mode",
            help="Sync mode: pr or local",
        ),
    ] = None,
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
        resolved_config = resolve_config_path(config)
        resolved_site = resolve_config_path(site_config)
        selected_mode = mode or resolve_sync_mode(resolved_config)
        result = sync_site(
            config_path=resolved_config,
            site_config_path=resolved_site,
            mode=selected_mode,
            publish_config_path=resolved_config.parent / "publish.yaml",
        )
    except (FileNotFoundError, SyncError, RenderError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_sync_summary(result)
