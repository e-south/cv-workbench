"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ingestion/strategy.py

Builds draft variant strategy payloads for ingested contexts.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from typing import Any


def build_strategy(context_id: str, signals: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy": {
            "context_id": context_id,
            "include_tags": [],
            "exclude_tags": [],
            "keyword_hints": signals.get("keywords", []),
        }
    }
