"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/project_guidance.py

Read optional project-plan metadata and summarize recommendation text.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_optional_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, None
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON at {path}: {exc.msg}"
    if not isinstance(raw, dict):
        return None, f"Optional JSON payload must be an object: {path}"
    return raw, None


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
