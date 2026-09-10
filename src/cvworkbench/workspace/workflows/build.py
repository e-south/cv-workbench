"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/workflows/build.py

Describe build workflow preconditions, commands, outputs, and stop conditions.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cvworkbench.workspace.commands import recipe_command


def baseline_build_preview_recipe(
    *, config_path: Path, sot_path: Path | None, configured_sot_path: str | None, variant_label: str
) -> dict[str, Any]:
    return {
        "id": "baseline.build_preview",
        "title": "Baseline build and preview",
        "preconditions": [
            "sot.status == 'ready'",
            "variants.default is available",
        ],
        "steps": [
            {
                "command": recipe_command(
                    "status --plain",
                    config_path=config_path,
                    sot_path=sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Summarize SoT sections, tags, and configured variants.",
            },
            {
                "command": recipe_command(
                    f"build --variant {variant_label} --format md,pdf",
                    config_path=config_path,
                    sot_path=sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Generate markdown and PDF outputs for the default variant.",
            },
            {
                "command": recipe_command(
                    f"preview --variant {variant_label}",
                    config_path=config_path,
                    sot_path=sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Start the local preview server for the default variant.",
            },
        ],
        "outputs": [
            "var/dist/<variant>/cv.md",
            "var/dist/<variant>/cv.pdf",
            "var/runs/<run-id>/manifest.json",
            "var/runs/<run-id>/canonical.md",
        ],
        "stop_conditions": [
            "If SoT is missing or invalid, ask for the correct --sot-path or config update.",
        ],
    }


def automation_verify_recipe(
    *, config_path: Path, sot_path: Path | None, configured_sot_path: str | None, variant_label: str
) -> dict[str, Any]:
    return {
        "id": "automation.verify",
        "title": "Automation-friendly smoke verification",
        "preconditions": [
            "sot.status == 'ready'",
            "variants.default is available",
        ],
        "steps": [
            {
                "command": recipe_command(
                    "status --plain",
                    config_path=config_path,
                    sot_path=sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Capture the current workspace summary before running smoke checks.",
            },
            {
                "command": recipe_command(
                    f"build --variant {variant_label} --format md",
                    config_path=config_path,
                    sot_path=sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Generate the lightweight markdown artifact for deterministic verification.",
            },
            {
                "command": recipe_command(
                    f"preview --variant {variant_label} --once",
                    config_path=config_path,
                    sot_path=sot_path,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Render one-shot HTML output without starting a long-lived preview server.",
            },
        ],
        "outputs": [
            "var/dist/<variant>/cv.md",
            "var/dist/<variant>/cv.html",
            "var/runs/<run-id>/manifest.json",
            "var/runs/<run-id>/canonical.md",
        ],
        "stop_conditions": [
            "Use baseline.build_preview if you need PDF output or a live preview server.",
        ],
    }
