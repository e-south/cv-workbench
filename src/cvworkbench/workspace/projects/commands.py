"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/projects/commands.py

Describe available project commands without executing them.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from cvworkbench.config import ConfigSource, resolve_config_path
from cvworkbench.ops.projects import suggest_project_variant_id
from cvworkbench.workspace.commands import recipe_command


def project_commands(
    project_id: str,
    *,
    config_path: ConfigSource,
    variant_id: str | None = None,
    review_run_id: str | None = None,
    sot_path: Path | None = None,
    proposal_available: bool = True,
) -> dict[str, str]:
    configuration = config_path
    config_path = resolve_config_path(configuration)
    commands = {
        "show": recipe_command(
            f"project show {project_id}",
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
                    f"preview --project {project_id}",
                    config_path=config_path,
                    sot_path=sot_path,
                ),
                "build": recipe_command(
                    f"build --project {project_id} --format md,pdf,docx",
                    config_path=config_path,
                    sot_path=sot_path,
                ),
                "apply": recipe_command(
                    f"project apply {project_id}",
                    config_path=config_path,
                    sot_path=sot_path,
                ),
                "keep": recipe_command(
                    f"variant keep --project {project_id} --id {keep_variant_id}",
                    config_path=config_path,
                    sot_path=None,
                ),
                "discard": recipe_command(
                    f"variant discard --project {project_id} --yes",
                    config_path=config_path,
                    sot_path=None,
                ),
            }
        )
    if review_run_id is not None:
        commands["reviewpack"] = recipe_command(
            f"reviewpack --project {project_id} --run {review_run_id}",
            config_path=config_path,
            sot_path=None,
        )
    return commands
