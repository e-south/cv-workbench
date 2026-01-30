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
import signal
import socket
import time
from pathlib import Path
from typing import Annotated, Any
from urllib import error as url_error
from urllib import request as url_request

import typer

from cvworkbench.build.explain import ExplainError, explain_item, load_selection
from cvworkbench.build.paths import filters_dir, output_path
from cvworkbench.build.pipeline import BuildResult, build_documents, create_run_dir
from cvworkbench.build.rendering import RenderError, render_document
from cvworkbench.build.styles import prepare_html_style
from cvworkbench.cli.helpers import configure_output_mode, load_sot_payload, resolve_selection_path
from cvworkbench.cli.output import OutputMode, get_output_mode, print_summary
from cvworkbench.config import (
    resolve_config_path,
    resolve_default_theme,
    resolve_default_variant,
    resolve_dist_path,
    resolve_drafts_path,
    resolve_pdf_engine,
    resolve_project_path,
    resolve_runs_path,
    resolve_sot_path,
    resolve_style_preset,
    resolve_sync_mode,
    resolve_themes_dir,
    resolve_variant_path,
)
from cvworkbench.dev.open import (
    OpenMode,
    OpenResult,
    PreviewViewer,
    open_pdf_in_preview,
    open_pdf,
    open_url,
    resolve_open_mode,
    resolve_preview_viewer,
)
from cvworkbench.dev.preview import (
    PreviewController,
    PreviewError,
    clear_preview_session,
    load_preview_session,
    new_preview_session,
    serve_preview,
    write_preview_session,
)
from cvworkbench.ingestion.registry import RegistryError, add_url_context
from cvworkbench.inputs.sot_versions import (
    SotVersionError,
    resolve_active_sot_path,
    resolve_versioned_root,
)
from cvworkbench.inputs.tags import extract_tags, lint_tags, tag_counts
from cvworkbench.inputs.validation import validate_sot
from cvworkbench.ops.apply import ApplyError, apply_draft
from cvworkbench.ops.clean import CleanError, clean_path
from cvworkbench.ops.diffing import DiffError, DiffSelection, diff_artifacts, parse_artifact
from cvworkbench.ops.doctor import run_doctor
from cvworkbench.ops.projects import (
    ProjectError,
    apply_project_patch,
    create_project_from_file,
    create_project_from_url,
    load_project,
    prepare_project_sot,
    resolve_project_dir,
)
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
project_app = typer.Typer(no_args_is_help=True)
app.add_typer(job_app, name="job")
app.add_typer(tags_app, name="tags")
app.add_typer(theme_app, name="theme")
app.add_typer(dev_app, name="dev")
app.add_typer(variant_app, name="variant")
app.add_typer(clean_app, name="clean")
app.add_typer(sot_app, name="sot")
app.add_typer(project_app, name="project")


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
    open_mode: OpenMode,
    viewer: PreviewViewer,
) -> None:
    print_summary(
        "serve",
        [
            ("output_html", output_path),
            ("preview_url", preview_url),
            ("opened_browser", str(opened).lower()),
            ("watching", str(watching).lower()),
            ("open_mode", open_mode.value),
            ("viewer", viewer.value),
            ("controls", "t=theme p=preset v=variant f=format r=rebuild x=stop"),
        ],
    )


_open_url = open_url


def _print_open_hint(target: str | Path) -> None:
    typer.echo(f"HINT: open {target}", err=True)


def _normalize_open_target(target: str | Path) -> str:
    if isinstance(target, Path):
        if target.exists():
            return str(target.resolve())
        return str(target)
    if target.startswith(("http://", "https://", "file://")):
        return target
    path = Path(target)
    if path.exists():
        return str(path.resolve())
    return target


def _open_preview_url(url: str | Path, open_mode: OpenMode, browser: str | None) -> OpenResult:
    target = _normalize_open_target(url)
    result = _open_url(target, mode=open_mode, browser=browser)
    if result.note:
        typer.echo(f"NOTICE: {result.note}", err=True)
    return result


def _post_preview_stop(url: str, timeout: float = 2.0) -> tuple[bool, str | None]:
    endpoint = url.rstrip("/") + "/api/stop"
    try:
        req = url_request.Request(endpoint, method="POST")
        with url_request.urlopen(req, timeout=timeout) as response:
            if 200 <= response.status < 300:
                return True, None
            return False, f"Preview stop failed with HTTP {response.status}"
    except (url_error.URLError, ValueError) as exc:
        return False, str(exc)


def _wait_for_port_close(host: str, port: int, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                pass
        except OSError:
            return True
        time.sleep(0.1)
    return False


def _terminate_preview_process(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        typer.echo(f"ERROR: Failed to terminate preview process: {exc}", err=True)
        raise typer.Exit(code=1) from exc


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


def _print_project_new_summary(
    *,
    project_dir: Path,
    variant_id: str,
    job_source: str,
) -> None:
    print_summary(
        "project.new",
        [
            ("project_dir", project_dir),
            ("variant", variant_id),
            ("job_source", job_source),
            ("next_step", f"cvw preview --project {project_dir.name}"),
        ],
    )


def _print_project_apply_summary(project_dir: Path, sot_path: Path) -> None:
    print_summary(
        "project.apply",
        [
            ("project_dir", project_dir),
            ("sot_path", sot_path),
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


@project_app.command("new")
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
    open_mode: Annotated[
        OpenMode | None,
        typer.Option(
            "--open-mode",
            help="Browser open mode (launchservices, applescript, none)",
            envvar="CVW_OPEN_MODE",
        ),
    ] = None,
    viewer: Annotated[
        PreviewViewer | None,
        typer.Option(
            "--viewer",
            help="Preview viewer (browser, preview-app, quicklook-pdf, none)",
            envvar="CVW_PREVIEW_VIEWER",
        ),
    ] = None,
    browser: Annotated[
        str | None,
        typer.Option(
            "--browser",
            help="Browser app name (macOS) or opener command",
            envvar="CVW_BROWSER",
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
    if bool(job_url) == bool(job_file):
        typer.echo("ERROR: Provide exactly one of --job-url or --job-file", err=True)
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

    _print_project_new_summary(
        project_dir=result.project_dir,
        variant_id=base_variant,
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
            viewer=viewer,
            open_mode=open_mode,
            browser=browser,
            project=result.project_dir.name,
        )


@project_app.command("apply")
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
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path",
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
    project_spec = None
    variant_path_override = None
    run_dir = None
    if project:
        config_path = resolve_config_path(config)
        project_dir = resolve_project_dir(project, config_path)
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
                resolved = resolve_sot_path(sot_path, config_path)
            except (FileNotFoundError, ValueError) as exc:
                typer.echo(f"ERROR: {exc}", err=True)
                raise typer.Exit(code=1) from exc
        runs_root = resolve_runs_path(config_path) / "projects" / project_spec.project_id
        runs_root.mkdir(parents=True, exist_ok=True)
        run_dir = create_run_dir(runs_root)
        try:
            resolved = prepare_project_sot(
                project_dir=project_spec.project_dir,
                sot_path=resolved,
                run_dir=run_dir,
            )
        except ProjectError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    else:
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
            variant_path_override=variant_path_override,
            run_dir=run_dir,
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
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path",
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
    viewer: Annotated[
        PreviewViewer | None,
        typer.Option(
            "--viewer",
            help="Preview viewer (browser, preview-app, quicklook-pdf, none)",
            envvar="CVW_PREVIEW_VIEWER",
        ),
    ] = None,
    open_mode: Annotated[
        OpenMode | None,
        typer.Option(
            "--open-mode",
            help="Browser open mode (launchservices, applescript, none)",
            envvar="CVW_OPEN_MODE",
        ),
    ] = None,
    browser: Annotated[
        str | None,
        typer.Option(
            "--browser",
            help="Browser app name (macOS) or opener command",
            envvar="CVW_BROWSER",
        ),
    ] = None,
) -> None:
    configure_output_mode(plain, json_output)
    resolved_open_mode = resolve_open_mode(open_mode)
    resolved_viewer = resolve_preview_viewer(viewer)
    if resolved_open_mode == OpenMode.APPLESCRIPT and resolved_viewer in {
        PreviewViewer.QUICKLOOK_PDF,
        PreviewViewer.PREVIEW_APP,
    }:
        typer.echo(
            "ERROR: preview-app/quicklook-pdf viewers do not support open-mode applescript",
            err=True,
        )
        raise typer.Exit(code=2)
    config_path = resolve_config_path(config)
    project_spec = None
    try:
        if project:
            project_dir = resolve_project_dir(project, config_path)
            project_spec = load_project(project_dir)
            if variant:
                typer.echo("ERROR: --variant cannot be combined with --project", err=True)
                raise typer.Exit(code=2)
            if sot_path is not None:
                typer.echo("ERROR: --sot-path cannot be combined with --project", err=True)
                raise typer.Exit(code=2)
            resolved_variant_obj = load_variant(project_spec.variant_path)
            resolved_variant = resolved_variant_obj.id
            resolved = resolve_active_sot_path(project_spec.sot_path)
        else:
            resolved = resolve_sot_path(sot_path, config_path)
            resolved_variant = variant or resolve_default_variant(config_path)
            variant_path = resolve_variant_path(resolved_variant, config_path)
            resolved_variant_obj = load_variant(variant_path)
        resolved_theme = (
            theme or resolved_variant_obj.render_theme or resolve_default_theme(config_path)
        )
        resolved_preset = (
            style_preset
            or resolved_variant_obj.render_style_preset
            or resolve_style_preset(config_path)
        )
    except (FileNotFoundError, ValueError, SotVersionError, ProjectError) as exc:
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
        auto_pdf=True if resolved_viewer == PreviewViewer.QUICKLOOK_PDF else True,
        project_dir=project_spec.project_dir if project_spec else None,
    )
    host = os.environ.get("CVW_DEV_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("CVW_DEV_PORT", "8765"))
    except ValueError as exc:
        typer.echo("ERROR: CVW_DEV_PORT must be an integer", err=True)
        raise typer.Exit(code=1) from exc
    if os.environ.get("CVW_DEV_ONCE") == "1":
        try:
            state = controller.build_once()
        except PreviewError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        html_path = state.output_files.get("html", state.dist_dir / "cv.html")
        open_result = OpenResult(opened=False, error=None, mode=resolved_open_mode)
        if resolved_viewer != PreviewViewer.NONE and resolved_open_mode != OpenMode.NONE:
            if resolved_viewer == PreviewViewer.QUICKLOOK_PDF:
                pdf_path = state.output_files.get("pdf", state.dist_dir / "cv.pdf")
                open_result = open_pdf(pdf_path)
                if not open_result.opened and open_result.error:
                    typer.echo(f"ERROR: {open_result.error}", err=True)
                    _print_open_hint(pdf_path)
            elif resolved_viewer == PreviewViewer.PREVIEW_APP:
                pdf_path = state.output_files.get("pdf", state.dist_dir / "cv.pdf")
                open_result = open_pdf_in_preview(pdf_path)
                if not open_result.opened and open_result.error:
                    typer.echo(f"ERROR: {open_result.error}", err=True)
                    _print_open_hint(pdf_path)
            else:
                open_result = _open_preview_url(html_path, resolved_open_mode, browser)
                if not open_result.opened and open_result.error:
                    typer.echo(f"ERROR: {open_result.error}", err=True)
                    _print_open_hint(html_path)
        _print_serve_summary(
            html_path,
            str(html_path),
            open_result.opened,
            False,
            resolved_open_mode,
            resolved_viewer,
        )
        return

    def _on_start(url: str, html_path: Path) -> None:
        open_result = OpenResult(opened=False, error=None, mode=resolved_open_mode)
        if resolved_viewer != PreviewViewer.NONE and resolved_open_mode != OpenMode.NONE:
            if resolved_viewer == PreviewViewer.QUICKLOOK_PDF:
                state = controller.state()
                pdf_path = state.output_files.get("pdf", state.dist_dir / "cv.pdf")
                open_result = open_pdf(pdf_path)
                if not open_result.opened and open_result.error:
                    typer.echo(f"ERROR: {open_result.error}", err=True)
                    _print_open_hint(pdf_path)
            elif resolved_viewer == PreviewViewer.PREVIEW_APP:
                state = controller.state()
                pdf_path = state.output_files.get("pdf", state.dist_dir / "cv.pdf")
                open_result = open_pdf_in_preview(pdf_path)
                if not open_result.opened and open_result.error:
                    typer.echo(f"ERROR: {open_result.error}", err=True)
                    _print_open_hint(pdf_path)
            else:
                open_result = _open_preview_url(url, resolved_open_mode, browser)
                if not open_result.opened and open_result.error:
                    typer.echo(f"ERROR: {open_result.error}", err=True)
                    _print_open_hint(url)
        session = new_preview_session(host=host, port=port, url=url, state=controller.state())
        write_preview_session(session, config_path)
        _print_serve_summary(
            html_path,
            url,
            open_result.opened,
            True,
            resolved_open_mode,
            resolved_viewer,
        )

    try:
        serve_preview(controller=controller, host=host, port=port, on_start=_on_start)
    except PreviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        if exc.errno in {48, 98, 10048}:
            typer.echo(f"ERROR: {exc}", err=True)
            typer.echo(
                "HINT: preview port is already in use. Run `cvw dev stop` or set CVW_DEV_PORT.",
                err=True,
            )
            raise typer.Exit(code=1) from exc
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    finally:
        clear_preview_session(config_path)


@dev_app.command("stop")
def dev_stop(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Force stop by terminating the preview process",
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
    config_path = resolve_config_path(config)
    try:
        session = load_preview_session(config_path)
    except PreviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    ok, error = _post_preview_stop(session.url)
    if not ok:
        if force:
            _terminate_preview_process(session.pid)
        else:
            typer.echo(f"ERROR: {error}", err=True)
            raise typer.Exit(code=1)

    if not _wait_for_port_close(session.host, session.port):
        if force:
            _terminate_preview_process(session.pid)
        else:
            typer.echo("ERROR: Preview server still running", err=True)
            raise typer.Exit(code=1)

    clear_preview_session(config_path)
    print_summary(
        "dev.stop",
        [
            ("status", "stopped"),
            ("host", session.host),
            ("port", session.port),
        ],
    )


@app.command()
def preview(
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
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path",
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
    viewer: Annotated[
        PreviewViewer | None,
        typer.Option(
            "--viewer",
            help="Preview viewer (browser, preview-app, quicklook-pdf, none)",
            envvar="CVW_PREVIEW_VIEWER",
        ),
    ] = None,
    open_mode: Annotated[
        OpenMode | None,
        typer.Option(
            "--open-mode",
            help="Browser open mode (launchservices, applescript, none)",
            envvar="CVW_OPEN_MODE",
        ),
    ] = None,
    browser: Annotated[
        str | None,
        typer.Option(
            "--browser",
            help="Browser app name (macOS) or opener command",
            envvar="CVW_BROWSER",
        ),
    ] = None,
) -> None:
    dev_serve(
        sot_path=sot_path,
        config=config,
        variant=variant,
        project=project,
        theme=theme,
        style_preset=style_preset,
        plain=plain,
        json_output=json_output,
        viewer=viewer,
        open_mode=open_mode,
        browser=browser,
    )


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
