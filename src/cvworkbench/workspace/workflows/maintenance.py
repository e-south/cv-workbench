"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/workflows/maintenance.py

Describe maintenance workflow preconditions, commands, outputs, and stop conditions.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cvworkbench.workspace.commands import recipe_command


def context_refresh_recipe(
    *, config_path: Path, sot_path: Path | None, configured_sot_path: str | None
) -> dict[str, Any]:
    return {
        "id": "context.refresh",
        "title": "Refresh context",
        "preconditions": [],
        "steps": [
            {
                "command": recipe_command(
                    "context --json",
                    config_path=config_path,
                    sot_path=sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Re-scan workspace state for SoT, variants, runs, and projects.",
            }
        ],
        "outputs": ["context payload (JSON)"],
        "stop_conditions": [],
    }


def variant_manage_recipe(*, config_path: Path, configured_sot_path: str | None) -> dict[str, Any]:
    return {
        "id": "variant.manage",
        "title": "Promote or discard variants",
        "preconditions": [],
        "steps": [
            {
                "command": recipe_command(
                    "variant inbox",
                    config_path=config_path,
                    sot_path=None,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "List ephemeral variants awaiting a keep/discard decision.",
            },
            {
                "command": recipe_command(
                    "variant keep --project <project-id> --id <variant-id>",
                    config_path=config_path,
                    sot_path=None,
                    configured_sot_path=configured_sot_path,
                ),
                "description": (
                    "Promote a project proposal into config/variants. "
                    "Use --path <variant.yaml> for manual or draft variants."
                ),
            },
            {
                "command": recipe_command(
                    "variant discard --project <project-id> --yes",
                    config_path=config_path,
                    sot_path=None,
                    configured_sot_path=configured_sot_path,
                ),
                "description": (
                    "Discard a project proposal after explicit approval. "
                    "Use --path <variant.yaml> for manual or draft variants."
                ),
            },
        ],
        "outputs": ["config/variants/<variant-id>.yaml", "var/variants/registry.json"],
        "stop_conditions": [
            "Never discard without explicit approval.",
        ],
    }


def runs_gc_recipe(*, config_path: Path, configured_sot_path: str | None) -> dict[str, Any]:
    return {
        "id": "runs.gc",
        "title": "Prune older runs",
        "preconditions": [],
        "steps": [
            {
                "command": recipe_command(
                    "runs gc --keep-latest 2",
                    config_path=config_path,
                    sot_path=None,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "See which runs would be removed (dry run).",
            },
            {
                "command": recipe_command(
                    "runs gc --keep-latest 2 --yes",
                    config_path=config_path,
                    sot_path=None,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Delete runs older than the keep window after approval.",
            },
        ],
        "outputs": ["var/runs/"],
        "stop_conditions": [
            "Never delete runs without explicit approval.",
        ],
    }
