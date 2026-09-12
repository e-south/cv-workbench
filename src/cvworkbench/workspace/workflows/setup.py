"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/workflows/setup.py

Describe setup workflow preconditions, commands, outputs, and stop conditions.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from cvworkbench.workspace.commands import init_command, recipe_command


def bootstrap_sample_workspace_recipe(
    *,
    config_path: Path,
    workspace_root: Path,
    configured_sot_path: str | None,
    sample_sot_path: Path | None,
    variant_label: str,
) -> dict[str, Any]:
    return {
        "id": "bootstrap.sample_workspace",
        "title": "Bootstrap with sample SoT",
        "preconditions": [
            "sot.status != 'ready'",
            f"sample SoT exists at {sample_sot_path}",
        ],
        "steps": [
            {
                "command": init_command(
                    sample_default=True,
                    workspace_root=workspace_root,
                ),
                "description": (
                    "Create missing scaffold files; retain any existing source configuration."
                ),
            },
            {
                "command": recipe_command(
                    "context --json",
                    config_path=config_path,
                    sot_path=sample_sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Confirm the workspace now resolves the sample SoT.",
            },
            {
                "command": recipe_command(
                    f"build --variant {variant_label} --format md,pdf",
                    config_path=config_path,
                    sot_path=sample_sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": (
                    "Build using the explicit sample SoT without changing the private source selection."
                ),
            },
        ],
        "outputs": [
            str(config_path),
            str(sample_sot_path),
            "var/dist/<variant>/cv.md",
            "var/runs/<run-id>/manifest.json",
        ],
        "stop_conditions": [
            "Use --sot-path or update config if you need a private SoT instead of the sample.",
        ],
    }


def bootstrap_local_workspace_recipe(
    *, config_path: Path, workspace_root: Path, configured_sot_path: str | None, variant_label: str
) -> dict[str, Any]:
    return {
        "id": "bootstrap.local_workspace",
        "title": "Recreate local scaffold",
        "preconditions": [
            "sot.status == 'missing'",
            "configured SoT points at ./local/sot",
            "sample SoT is not present",
        ],
        "steps": [
            {
                "command": init_command(
                    sample_default=False,
                    workspace_root=workspace_root,
                ),
                "description": (
                    "Recreate the local scaffold and copy the bundled sample into ./local/sot."
                ),
            },
            {
                "command": recipe_command(
                    "context --json",
                    config_path=config_path,
                    sot_path=None,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Confirm the workspace now resolves the recreated local SoT.",
            },
            {
                "command": recipe_command(
                    f"build --variant {variant_label} --format md,pdf",
                    config_path=config_path,
                    sot_path=None,
                    configured_sot_path=configured_sot_path,
                ),
                "description": ("Build using the recreated local SoT without passing --sot-path."),
            },
        ],
        "outputs": [
            "local/sot/",
            "config/workbench.yaml",
            "var/dist/<variant>/cv.md",
            "var/runs/<run-id>/manifest.json",
        ],
        "stop_conditions": [
            "Use --sot-path or update config if you need a different private SoT instead of the recreated local copy.",
        ],
    }


def repair_sot_path_recipe(*, config_path: Path, configured_sot_path: str | None) -> dict[str, Any]:
    return {
        "id": "repair.sot_path",
        "title": "Repair missing SoT path",
        "preconditions": [
            "sot.status == 'missing'",
        ],
        "steps": [
            {
                "command": recipe_command(
                    "validate --sot-path <path-to-sot>",
                    config_path=config_path,
                    sot_path=None,
                    configured_sot_path=configured_sot_path,
                ),
                "description": (
                    "Check the candidate SoT path before changing config or rerunning build commands."
                ),
            },
            {
                "command": shlex.join(["edit", str(config_path)]),
                "description": (
                    "Set paths.sot to the correct relative SoT path, or keep using --sot-path explicitly."
                ),
            },
            {
                "command": recipe_command(
                    "context --json --sot-path <path-to-sot>",
                    config_path=config_path,
                    sot_path=None,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Confirm the repaired SoT path resolves cleanly.",
            },
        ],
        "outputs": [
            "validated SoT path",
            str(config_path),
            "context payload (JSON)",
        ],
        "stop_conditions": [
            (
                "If sot.sample exists and you only need a demo workspace, "
                "use bootstrap.sample_workspace instead."
            ),
            "Do not run build or preview until validate succeeds.",
        ],
    }


def repair_sot_yaml_recipe(
    *, config_path: Path, sot_path: Path | None, configured_sot_path: str | None
) -> dict[str, Any]:
    return {
        "id": "repair.sot_yaml",
        "title": "Repair invalid SoT files",
        "preconditions": [
            "sot.status == 'invalid'",
        ],
        "steps": [
            {
                "command": recipe_command(
                    "validate",
                    config_path=config_path,
                    sot_path=sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Print the current YAML and schema validation errors.",
            },
            {
                "command": "edit <reported-file>.yaml",
                "description": "Fix the malformed YAML or schema violation reported by validate.",
            },
            {
                "command": recipe_command(
                    "validate",
                    config_path=config_path,
                    sot_path=sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Re-run validation until it passes cleanly.",
            },
            {
                "command": recipe_command(
                    "context --json",
                    config_path=config_path,
                    sot_path=sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Refresh context after the SoT validates successfully again.",
            },
        ],
        "outputs": [
            "validated SoT files",
            "context payload (JSON)",
        ],
        "stop_conditions": [
            "Do not run build or preview until validate succeeds.",
        ],
    }
