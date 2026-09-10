"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/reviews.py

Describe content-review inventory and recorded source health.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from typing import Any

from cvworkbench.config import ConfigSource
from cvworkbench.ops.review.catalog import list_review_summaries


def reviews_summary_line(reviews: list[dict[str, Any]]) -> str:
    if not reviews:
        return "count=0"
    lines = [
        item["review_id"]
        + (
            f" | source={item['source']['state']}"
            + (f" | run={item['source']['run_id']}" if item["source"]["run_id"] else "")
            if item.get("source")
            else ""
        )
        for item in reviews
    ]
    return f"count={len(reviews)}\n" + "\n".join(lines)


def build_reviews_context(config_path: ConfigSource, *, include_items: bool) -> dict[str, Any]:
    reviews = list_review_summaries(config_path)
    section: dict[str, Any] = {
        "count": len(reviews),
        "summary": reviews_summary_line(reviews),
    }
    if include_items:
        section["items"] = reviews
    return section
