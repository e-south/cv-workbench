"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/styles.py

Helpers for preparing style assets for rendered outputs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

from cvworkbench.themes import RenderPlan


def prepare_html_style(
    dist_dir: Path,
    plan: RenderPlan,
    theme_id: str,
    preset: str | None,
) -> RenderPlan:
    if plan.style_kind != "css" or plan.style_path is None:
        return plan
    preset_id = preset or "default"
    styles_dir = dist_dir / "styles"
    styles_dir.mkdir(parents=True, exist_ok=True)
    target_name = f"{theme_id}-{preset_id}.css"
    target_path = styles_dir / target_name
    shutil.copy2(plan.style_path, target_path)
    relative_path = Path("styles") / target_name
    return replace(plan, style_path=relative_path)
