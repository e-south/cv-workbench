"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/projects/commands.py

Describe available project commands without executing them.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import shlex
from pathlib import Path

from cvworkbench.config import ConfigSource, read_config
from cvworkbench.ops.projects import resolve_project_dir, suggest_project_variant_id
from cvworkbench.ops.projects.identity import validate_project_id
from cvworkbench.workspace.commands import recipe_command


def project_selector(project_id: str, *, project_dir: Path, config_path: ConfigSource) -> str:
    """Use an ID only when its configured mapping selects the described directory."""
    validate_project_id(project_id)
    selected = project_dir.resolve()
    configured = resolve_project_dir(project_id, config_path)
    return project_id if selected == configured else str(selected)


def project_commands(
    project_id: str,
    *,
    project_dir: Path,
    config_path: ConfigSource,
    variant_id: str | None = None,
    review_run_id: str | None = None,
    sot_path: Path | None = None,
    proposal_available: bool = True,
) -> dict[str, str]:
    configuration = read_config(config_path)
    config_path = configuration.path
    selector = shlex.quote(
        project_selector(project_id, project_dir=project_dir, config_path=configuration)
    )
    commands = {
        "show": recipe_command(
            f"project show {selector}",
            config_path=config_path,
            sot_path=None,
        ),
    }
    if proposal_available:
        keep_variant_id = suggest_project_variant_id(
            project_id=project_id,
            config_path=configuration,
            preferred_id=variant_id,
        )
        commands.update(
            {
                "preview": recipe_command(
                    f"preview --project {selector}",
                    config_path=config_path,
                    sot_path=sot_path,
                ),
                "build": recipe_command(
                    f"build --project {selector} --format md,pdf,docx",
                    config_path=config_path,
                    sot_path=sot_path,
                ),
                "apply": recipe_command(
                    f"project apply {selector}",
                    config_path=config_path,
                    sot_path=sot_path,
                ),
                "keep": recipe_command(
                    f"variant keep --project {selector} --id {shlex.quote(keep_variant_id)}",
                    config_path=config_path,
                    sot_path=None,
                ),
                "discard": recipe_command(
                    f"variant discard --project {selector} --yes",
                    config_path=config_path,
                    sot_path=None,
                ),
            }
        )
    if review_run_id is not None:
        commands["reviewpack"] = recipe_command(
            f"reviewpack --project {selector} --run {shlex.quote(review_run_id)}",
            config_path=config_path,
            sot_path=None,
        )
    return commands
