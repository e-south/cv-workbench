"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/project_guidance.py

Explain saved project guidance and summarize recommendation text.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from typing import Any

from cvworkbench.variants import validate_variant_id


def proposal_plan_selection_warning(
    plan: dict[str, Any] | None, current_base_variant: str
) -> str | None:
    if plan is None:
        return None
    recorded = plan.get("applied_variant")
    try:
        validate_variant_id(recorded)
    except ValueError:
        return (
            "Saved guidance does not identify an applied variant. "
            "Compare its recommendations with the current proposal before using them."
        )
    if recorded != current_base_variant:
        return (
            f"Saved guidance was recorded for '{recorded}'; "
            f"the current base variant is '{current_base_variant}'. "
            "Review its recommendations before using them."
        )
    return None


def recommendations_summary_line(recommendations: list[dict[str, Any]], limit: int = 5) -> str:
    if not recommendations:
        return "none"
    lines: list[str] = []
    for item in recommendations[:limit]:
        parts = [item["variant_id"], f"score={item['score']}"]
        if item.get("default"):
            parts.append("default")
        if item.get("include_matches"):
            parts.append("match=" + ",".join(item["include_matches"]))
        if item.get("rationale"):
            parts.append("why=" + item["rationale"][0])
        if item.get("exclude_matches"):
            parts.append("exclude=" + ",".join(item["exclude_matches"]))
        if item.get("missing_in_sot"):
            parts.append("missing_sot=" + ",".join(item["missing_in_sot"]))
        lines.append(" | ".join(parts))
    return "\n".join(lines)
