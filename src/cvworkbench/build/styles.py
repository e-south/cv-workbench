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
    relative_path = html_style_path(theme_id, preset)
    target_path = dist_dir / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(plan.style_path, target_path)
    return replace(plan, style_path=relative_path)


def html_style_path(theme_id: str, preset: str | None) -> Path:
    return Path("styles") / f"{theme_id}-{preset or 'default'}.css"
