"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/commands/setup.py

Adapt source validation, toolchain checks, and workspace setup commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cvworkbench.build.paths import output_path
from cvworkbench.build.pipeline import BuildResult, build_documents
from cvworkbench.build.rendering import (
    RenderError,
)
from cvworkbench.cli.helpers import _validate_sot, configure_output_mode
from cvworkbench.cli.output import print_summary
from cvworkbench.config import (
    resolve_config_path,
    resolve_project_root,
    resolve_sot_path,
)
from cvworkbench.ops.doctor import run_doctor
from cvworkbench.ops.scaffold import ScaffoldError, init_project, resolve_template_root
from cvworkbench.themes import (
    ThemeError,
)
from cvworkbench.workspace.commands import shell_command


def _print_validate_summary(sot_path: Path) -> None:
    print_summary(
        "validate",
        [
            ("status", "ok"),
            ("sot_path", sot_path),
        ],
    )


def _print_doctor_summary(rows: list[tuple[str, str | Path]]) -> None:
    print_summary("doctor", rows)


def _print_init_summary(result: dict[str, str | Path]) -> None:
    rows = [(key, value) for key, value in result.items()]
    print_summary("init", rows)


def _resolve_workspace_root(config: Path = Path("config/workbench.yaml")) -> Path:
    try:
        return resolve_project_root(resolve_config_path(config))
    except FileNotFoundError:
        return Path.cwd()


def _print_quickstart_summary(
    result: BuildResult,
    sample_sot: Path,
    *,
    use_configured_sot: bool,
) -> None:
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
    if use_configured_sot:
        rows.append(("next_step", shell_command(f"preview --variant {result.variant.id}")))
    else:
        rows.append(
            (
                "next_step",
                shell_command(f"preview --sot-path {sample_sot} --variant {result.variant.id}"),
            )
        )
    for fmt in result.formats:
        rows.append((f"output_{fmt}", output_path(result.dist_dir, result.variant, fmt)))
    print_summary("quickstart", rows)


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

    errors = _validate_sot(resolved)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)
    _print_validate_summary(resolved)


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


def init(
    workspace: Annotated[
        Path | None,
        typer.Option(
            "--workspace",
            help="Workspace root to initialize when running outside the target directory",
        ),
    ] = None,
    sample_default: Annotated[
        bool,
        typer.Option(
            "--sample-default",
            help="Use ./sot.sample as the configured default SoT instead of copying it to local/sot",
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
    root = workspace.resolve() if workspace is not None else _resolve_workspace_root()
    try:
        result = init_project(root, sample_default=sample_default)
    except ScaffoldError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    statuses = result.statuses
    summary = {
        "root": result.root,
        "sot_path": result.sot_path,
        "sot_profile": statuses.get("sot_profile", "local-copy"),
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
        "pre_commit_hooks": statuses.get("pre_commit_hooks", "unknown"),
    }
    if statuses.get("pre_commit_hooks_detail"):
        summary["pre_commit_hooks_detail"] = statuses["pre_commit_hooks_detail"]
    _print_init_summary(summary)


def quickstart(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    sample_default: Annotated[
        bool,
        typer.Option(
            "--sample-default",
            help="Use ./sot.sample as the configured default SoT after scaffold setup",
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
    workspace_root = _resolve_workspace_root(config)
    resolved_config = config if config.is_absolute() else workspace_root / config
    try:
        init_project(workspace_root, sample_default=sample_default)
    except ScaffoldError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    template_root = resolve_template_root()
    sample_sot = template_root / "sot.sample"
    use_configured_sot = False
    try:
        configured_sot = resolve_sot_path(None, resolved_config)
    except (FileNotFoundError, ValueError):
        configured_sot = None
    if (
        configured_sot is not None
        and configured_sot.exists()
        and configured_sot.name == "sot.sample"
    ):
        sample_sot = configured_sot
        use_configured_sot = True
    if not sample_sot.exists():
        typer.echo(f"ERROR: Sample SoT not found: {sample_sot}", err=True)
        raise typer.Exit(code=1)

    errors = _validate_sot(sample_sot)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)

    try:
        result = build_documents(
            sot_path=sample_sot,
            config_path=resolved_config,
            variant_id="base",
            formats=["md", "pdf", "docx"],
        )
    except (ValueError, RenderError, ThemeError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_quickstart_summary(result, sample_sot, use_configured_sot=use_configured_sot)
