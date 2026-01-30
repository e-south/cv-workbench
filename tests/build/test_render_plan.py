"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_render_plan.py

Tests render plan defaults for special formats.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from cvworkbench.themes import build_render_plan


def test_build_render_plan_for_ats() -> None:
    plan = build_render_plan(
        output_format="ats",
        theme=None,
        style_preset=None,
        pdf_engine=None,
    )

    assert plan.to == "plain"
