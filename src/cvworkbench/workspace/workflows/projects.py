"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/workflows/projects.py

Describe projects workflow preconditions, commands, outputs, and stop conditions.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cvworkbench.workspace.commands import recipe_command


def project_guide_recipe(
    *, config_path: Path, sot_path: Path | None, configured_sot_path: str | None, project_label: str
) -> dict[str, Any]:
    return {
        "id": "project.guide",
        "title": "Job tailoring project",
        "preconditions": [
            "sot.status == 'ready'",
            "job input (URL or file) provided",
        ],
        "steps": [
            {
                "command": recipe_command(
                    "project guide --job-file <job-file>",
                    config_path=config_path,
                    sot_path=sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Ingest a local job description file and get variant recommendations. Use --job-url <job-url> for remote postings.",
            },
            {
                "command": recipe_command(
                    f"project show {project_label}",
                    config_path=config_path,
                    sot_path=None,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Inspect the project proposal, patch status, and ready-to-run next commands.",
            },
            {
                "command": recipe_command(
                    f"preview --project {project_label}",
                    config_path=config_path,
                    sot_path=sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Preview with the project patch applied in-memory.",
            },
            {
                "command": recipe_command(
                    f"project apply {project_label}",
                    config_path=config_path,
                    sot_path=sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Apply the project patch after explicit approval.",
            },
        ],
        "outputs": [
            "var/projects/<slug>/project.yaml",
            "var/projects/<slug>/proposals/variant.yaml",
            "var/projects/<slug>/proposals/patch.yaml",
        ],
        "stop_conditions": [
            "If job input is missing, ask for a job URL or file.",
            "Only apply project patches after explicit approval.",
        ],
    }


def project_inspect_recipe(
    *, config_path: Path, sot_path: Path | None, configured_sot_path: str | None, project_label: str
) -> dict[str, Any]:
    return {
        "id": "project.inspect",
        "title": "Inspect project proposal",
        "preconditions": [
            "project workspace exists",
        ],
        "steps": [
            {
                "command": recipe_command(
                    f"project show {project_label}",
                    config_path=config_path,
                    sot_path=None,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Summarize the proposal variant, patch status, job source, and next commands.",
            },
            {
                "command": recipe_command(
                    f"preview --project {project_label}",
                    config_path=config_path,
                    sot_path=sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Preview with the project patch applied in-memory.",
            },
        ],
        "outputs": [
            "project summary",
            "var/projects/<slug>/project.yaml",
            "var/projects/<slug>/proposals/variant.yaml",
            "var/projects/<slug>/proposals/patch.yaml",
        ],
        "stop_conditions": [
            "Only apply project patches after explicit approval.",
        ],
    }
