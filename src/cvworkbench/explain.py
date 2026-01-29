"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/explain.py

Loads selection metadata and resolves explain requests.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ExplainError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExplainedItem:
    item: dict[str, Any]


def load_selection(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ExplainError(f"Selection file not found: {path}")
    return json.loads(path.read_text())


def explain_item(
    selection: dict[str, Any],
    item_id: str,
    item_type: str | None,
) -> ExplainedItem:
    items = selection.get("items")
    if not isinstance(items, list):
        raise ExplainError("Selection file missing items list")

    matches = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("id") != item_id:
            continue
        if item_type and item.get("type") != item_type:
            continue
        matches.append(item)

    if not matches:
        raise ExplainError(f"Selection item not found: {item_id}")
    if len(matches) > 1:
        raise ExplainError(f"Multiple items matched id '{item_id}'; provide --type")
    return ExplainedItem(item=matches[0])
