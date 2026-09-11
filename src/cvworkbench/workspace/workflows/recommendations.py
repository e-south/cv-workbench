"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/workflows/recommendations.py

Workflows recommendations for workspace inspection and workflow guidance.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cvworkbench.ops.publication.state import PublicationState
from cvworkbench.workspace.commands import workflow_command
from cvworkbench.workspace.runs import run_is_review_ready


def build_recommended_workflows(
    *,
    recipes: list[dict[str, Any]],
    sot_status: str,
    latest_runs: dict[str, list[dict[str, Any]]],
    default_variant: str | None,
    config_path: Path,
    sot_path: Path | None,
    publication: PublicationState | None = None,
) -> list[dict[str, str]]:
    recipe_lookup = {recipe["id"]: recipe for recipe in recipes}
    recommendations: list[dict[str, str]] = []

    def add(recipe_id: str, reason: str) -> None:
        recipe = recipe_lookup.get(recipe_id)
        if recipe is None:
            return
        recommendations.append(
            {
                "id": recipe_id,
                "title": recipe["title"],
                "reason": reason,
                "command": workflow_command(
                    recipe_id,
                    config_path=config_path,
                    sot_path=sot_path,
                ),
                "json_command": workflow_command(
                    recipe_id,
                    config_path=config_path,
                    sot_path=sot_path,
                    json_output=True,
                    compact=True,
                ),
            }
        )

    if sot_status == "missing":
        add(
            "bootstrap.sample_workspace",
            "Fastest explicit path to a ready sample workspace when a local sample SoT is available.",
        )
        add(
            "bootstrap.local_workspace",
            "Recreate the default local scaffold when the workspace expects ./local/sot.",
        )
        add(
            "repair.sot_path",
            "Fix the configured SoT path or provide an explicit --sot-path before retrying build or preview.",
        )
        add(
            "context.refresh",
            "Refresh workspace state after repairing the configured SoT path.",
        )
        return recommendations

    if sot_status == "invalid":
        add(
            "repair.sot_yaml",
            "Fix the reported YAML or schema errors in the configured SoT before retrying build or preview.",
        )
        add(
            "context.refresh",
            "Refresh workspace state after the SoT validates cleanly again.",
        )
        return recommendations

    if publication is not None and publication.state != "unconfigured":
        add(
            "native.publish" if publication.source_kind == "native" else "authored.publish",
            "Inspect publication freshness and review before site handoff.",
        )

    add(
        "automation.verify",
        "Fastest deterministic smoke path for a ready workspace.",
    )
    add(
        "baseline.build_preview",
        "Use when you need PDF output or a live preview server instead of one-shot HTML.",
    )
    if default_variant is not None:
        candidate_runs = latest_runs.get(default_variant, [])
    else:
        candidate_runs = [run for runs in latest_runs.values() for run in runs]
    has_review_ready_runs = any(run_is_review_ready(run) for run in candidate_runs)
    if has_review_ready_runs:
        add(
            "review.import",
            "Available after a successful build when you need the DOCX review and import loop.",
        )
    else:
        add(
            "project.guide",
            "Start here when you are tailoring the workspace to a specific job or role.",
        )
    return recommendations[:3]
