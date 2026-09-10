"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/commands.py

Construct quoted command descriptions for the active installation and workspace.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import shlex
from pathlib import Path


def _default_config_path() -> Path:
    return (Path.cwd() / "config" / "workbench.yaml").resolve()


def _source_project_root() -> Path | None:
    candidate = Path(__file__).resolve().parents[3]
    if (candidate / "pyproject.toml").exists():
        return candidate
    return None


def command_prefix() -> list[str]:
    project_root = _source_project_root()
    if project_root is not None:
        try:
            Path.cwd().resolve().relative_to(project_root)
        except ValueError:
            return ["uv", "run", "--project", str(project_root), "cvw"]
        return ["uv", "run", "cvw"]
    return ["cvw"]


def shell_command(subcommand: str) -> str:
    return shlex.join([*command_prefix(), *shlex.split(subcommand)])


def recipe_command(
    subcommand: str,
    *,
    config_path: Path,
    sot_path: Path | str | None,
    configured_sot_path: str | None = None,
) -> str:
    command = [*command_prefix(), *shlex.split(subcommand)]
    if config_path != _default_config_path():
        command.extend(["--config", str(config_path)])
    if sot_path is not None:
        if isinstance(sot_path, Path):
            resolved_sot = sot_path.resolve()
            configured_sot = (
                Path(configured_sot_path).resolve() if configured_sot_path is not None else None
            )
            if configured_sot != resolved_sot:
                command.extend(["--sot-path", str(resolved_sot)])
        else:
            command.extend(["--sot-path", sot_path])
    return shlex.join(command)


def init_command(*, sample_default: bool, workspace_root: Path) -> str:
    command = [*command_prefix(), "init"]
    if sample_default:
        command.append("--sample-default")
    project_root = _source_project_root()
    if project_root is None or workspace_root.resolve() != Path.cwd().resolve():
        command.extend(["--workspace", str(workspace_root.resolve())])
    return shlex.join(command)


def workflow_command(
    recipe_id: str,
    *,
    config_path: Path,
    sot_path: Path | None,
    json_output: bool = False,
    compact: bool = False,
) -> str:
    if compact and not json_output:
        raise ValueError("compact workflow commands require json_output=True")
    command = [*command_prefix(), "workflow", "--id", recipe_id]
    if json_output:
        command.append("--json")
    if compact:
        command.append("--compact")

    if config_path != _default_config_path():
        command.extend(["--config", str(config_path)])

    if sot_path is not None:
        resolved_sot = sot_path if sot_path.is_absolute() else (Path.cwd() / sot_path).resolve()
        command.extend(["--sot-path", str(resolved_sot)])

    return shlex.join(command)
