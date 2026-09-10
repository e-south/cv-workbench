"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/workflows/steps.py

Workflows steps for workspace inspection and workflow guidance.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import re
from typing import Any

_RECIPE_PLACEHOLDER_RE = re.compile(r"<[^>]+>")


def _recipe_step(command: str, description: str) -> dict[str, Any]:
    placeholders = _RECIPE_PLACEHOLDER_RE.findall(command)
    kind = "manual" if command.startswith("edit ") else "command"
    return {
        "command": command,
        "description": description,
        "kind": kind,
        "runnable": kind == "command" and not placeholders,
        "placeholders": placeholders,
    }


def finalize_recipe_steps(recipes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for recipe in recipes:
        recipe["steps"] = [
            _recipe_step(step["command"], step["description"]) for step in recipe["steps"]
        ]
    return recipes
