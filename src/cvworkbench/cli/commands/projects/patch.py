"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/commands/projects/patch.py

Adapt structured project patch authoring commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from cvworkbench.cli.commands.projects.presentation import _print_project_patch_summary
from cvworkbench.cli.helpers import configure_output_mode
from cvworkbench.cli.output import OutputMode, get_output_mode
from cvworkbench.config import (
    resolve_config_path,
)
from cvworkbench.ops.projects import (
    ProjectError,
    append_replace_experience_bullet_operation,
    append_replace_project_summary_operation,
    load_project,
    resolve_project_dir,
)
from cvworkbench.workspace.projects import (
    project_commands,
)


def project_patch_replace_experience_bullet(
    project: Annotated[
        str,
        typer.Argument(help="Project id or path"),
    ],
    role_id: Annotated[
        str,
        typer.Option(
            "--role-id",
            help="Stable role id from experience.yaml",
        ),
    ],
    bullet_id: Annotated[
        str,
        typer.Option(
            "--bullet-id",
            help="Stable bullet id from experience.yaml",
        ),
    ],
    new_text: Annotated[
        str,
        typer.Option(
            "--new-text",
            help="Replacement bullet text",
        ),
    ],
    old_text: Annotated[
        str | None,
        typer.Option(
            "--old-text",
            help="Expected existing bullet text; defaults to the current SoT value",
        ),
    ] = None,
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Optional SoT override used for validation and source-text snapshotting",
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

    resolved_sot = sot_path.resolve() if sot_path is not None else spec.sot_path.resolve()
    if not resolved_sot.exists():
        typer.echo(f"ERROR: SoT path not found: {resolved_sot}", err=True)
        raise typer.Exit(code=1)

    try:
        patch = append_replace_experience_bullet_operation(
            project_dir=project_dir,
            sot_path=resolved_sot,
            role_id=role_id,
            bullet_id=bullet_id,
            new_text=new_text,
            old_text=old_text,
        )
    except ProjectError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    op_count = len(patch.operations)
    status = f"{op_count} op" if op_count == 1 else f"{op_count} ops"
    followup_sot = resolved_sot if resolved_sot != spec.sot_path.resolve() else None
    commands = project_commands(
        spec.project_id,
        project_dir=spec.project_dir,
        config_path=config_path,
        sot_path=followup_sot,
    )
    summary = {
        "command": "project.patch.replace-experience-bullet",
        "project": {
            "project_id": spec.project_id,
            "project_dir": str(spec.project_dir),
            "sot_path": str(resolved_sot),
        },
        "patch": {
            "path": str(spec.patch_path),
            "format": patch.format,
            "line_count": op_count,
            "status": status,
        },
        "operation": {
            "op": "replace-experience-bullet",
            "target": f"{role_id}:{bullet_id}",
            "role_id": role_id,
            "bullet_id": bullet_id,
            "old_text": patch.operations[-1]["old_text"],
            "new_text": patch.operations[-1]["new_text"],
        },
        "commands": commands,
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(summary, indent=2, sort_keys=True))
        return

    _print_project_patch_summary(summary)


def project_patch_replace_project_summary(
    project: Annotated[
        str,
        typer.Argument(help="Project id or path"),
    ],
    project_id: Annotated[
        str,
        typer.Option(
            "--project-id",
            help="Stable project id from projects.yaml",
        ),
    ],
    new_text: Annotated[
        str,
        typer.Option(
            "--new-text",
            help="Replacement project summary text",
        ),
    ],
    old_text: Annotated[
        str | None,
        typer.Option(
            "--old-text",
            help="Expected existing project summary; defaults to the current SoT value",
        ),
    ] = None,
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Optional SoT override used for validation and source-text snapshotting",
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

    resolved_sot = sot_path.resolve() if sot_path is not None else spec.sot_path.resolve()
    if not resolved_sot.exists():
        typer.echo(f"ERROR: SoT path not found: {resolved_sot}", err=True)
        raise typer.Exit(code=1)

    try:
        patch = append_replace_project_summary_operation(
            project_dir=project_dir,
            sot_path=resolved_sot,
            project_id=project_id,
            new_text=new_text,
            old_text=old_text,
        )
    except ProjectError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    op_count = len(patch.operations)
    status = f"{op_count} op" if op_count == 1 else f"{op_count} ops"
    followup_sot = resolved_sot if resolved_sot != spec.sot_path.resolve() else None
    commands = project_commands(
        spec.project_id,
        project_dir=spec.project_dir,
        config_path=config_path,
        sot_path=followup_sot,
    )
    summary = {
        "command": "project.patch.replace-project-summary",
        "project": {
            "project_id": spec.project_id,
            "project_dir": str(spec.project_dir),
            "sot_path": str(resolved_sot),
        },
        "patch": {
            "path": str(spec.patch_path),
            "format": patch.format,
            "line_count": op_count,
            "status": status,
        },
        "operation": {
            "op": "replace-project-summary",
            "target": project_id,
            "project_id": project_id,
            "old_text": patch.operations[-1]["old_text"],
            "new_text": patch.operations[-1]["new_text"],
        },
        "commands": commands,
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(summary, indent=2, sort_keys=True))
        return

    _print_project_patch_summary(summary)
