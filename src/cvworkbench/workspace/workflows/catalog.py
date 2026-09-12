"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/workflows/catalog.py

Workflows catalog for workspace inspection and workflow guidance.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cvworkbench.config import ConfigSource, read_config, resolve_drafts_path, resolve_reviews_path
from cvworkbench.workspace.source import is_local_scaffold_sot
from cvworkbench.workspace.workflows.build import (
    automation_verify_recipe,
    baseline_build_preview_recipe,
)
from cvworkbench.workspace.workflows.maintenance import (
    context_refresh_recipe,
    runs_gc_recipe,
    variant_manage_recipe,
)
from cvworkbench.workspace.workflows.projects import project_guide_recipe, project_inspect_recipe
from cvworkbench.workspace.workflows.review import review_import_recipe
from cvworkbench.workspace.workflows.setup import (
    bootstrap_local_workspace_recipe,
    bootstrap_sample_workspace_recipe,
    repair_sot_path_recipe,
    repair_sot_yaml_recipe,
)
from cvworkbench.workspace.workflows.steps import finalize_recipe_steps


def build_context_recipes(
    *,
    config_path: ConfigSource,
    workspace_root: Path,
    sot_path: Path | None,
    configured_sot_path: str | None,
    sot_status: str,
    sample_sot_path: Path | None,
    default_variant: str | None,
) -> list[dict[str, Any]]:
    configuration = read_config(config_path)
    config_path = configuration.path
    variant_label = default_variant or "<variant-id>"
    project_label = "<project-id>"
    recipes: list[dict[str, Any]] = []
    if sot_status == "missing" and sample_sot_path is not None:
        recipes.append(
            bootstrap_sample_workspace_recipe(
                config_path=config_path,
                workspace_root=workspace_root,
                configured_sot_path=configured_sot_path,
                sample_sot_path=sample_sot_path,
                variant_label=variant_label,
            )
        )
    if (
        sot_status == "missing"
        and sample_sot_path is None
        and is_local_scaffold_sot(configured_sot_path)
    ):
        recipes.append(
            bootstrap_local_workspace_recipe(
                config_path=config_path,
                workspace_root=workspace_root,
                configured_sot_path=configured_sot_path,
                variant_label=variant_label,
            )
        )
    if sot_status == "missing":
        recipes.append(
            repair_sot_path_recipe(config_path=config_path, configured_sot_path=configured_sot_path)
        )
    if sot_status == "invalid":
        recipes.append(
            repair_sot_yaml_recipe(
                config_path=config_path, sot_path=sot_path, configured_sot_path=configured_sot_path
            )
        )
    recipes.extend(
        [
            baseline_build_preview_recipe(
                config_path=config_path,
                sot_path=sot_path,
                configured_sot_path=configured_sot_path,
                variant_label=variant_label,
            ),
            automation_verify_recipe(
                config_path=config_path,
                sot_path=sot_path,
                configured_sot_path=configured_sot_path,
                variant_label=variant_label,
            ),
            review_import_recipe(
                config_path=config_path,
                reviews_path=resolve_reviews_path(configuration),
                drafts_path=resolve_drafts_path(configuration),
                sot_path=sot_path,
                configured_sot_path=configured_sot_path,
                variant_label=variant_label,
            ),
            project_guide_recipe(
                config_path=config_path,
                sot_path=sot_path,
                configured_sot_path=configured_sot_path,
                project_label=project_label,
            ),
            project_inspect_recipe(
                config_path=config_path,
                sot_path=sot_path,
                configured_sot_path=configured_sot_path,
                project_label=project_label,
            ),
            context_refresh_recipe(
                config_path=config_path, sot_path=sot_path, configured_sot_path=configured_sot_path
            ),
            variant_manage_recipe(config_path=config_path, configured_sot_path=configured_sot_path),
            runs_gc_recipe(config_path=config_path, configured_sot_path=configured_sot_path),
        ]
    )
    return finalize_recipe_steps(recipes)
