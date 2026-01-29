"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/inputs/tags.py

Collects tag metadata from Source of Truth data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from cvworkbench.text import normalize_tag, tag_classes


@dataclass(frozen=True)
class TagInfo:
    raw: str
    normalized: str
    classes: list[str]


def extract_tags(payload: dict[str, Any]) -> list[TagInfo]:
    tags: list[TagInfo] = []
    for raw_tag in _iter_tags(payload):
        normalized = normalize_tag(raw_tag)
        classes = tag_classes(raw_tag)
        tags.append(TagInfo(raw=raw_tag, normalized=normalized, classes=classes))
    return tags


def tag_counts(tags: Iterable[TagInfo]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for info in tags:
        for label in info.classes or [info.normalized]:
            if not label:
                continue
            counts[label] = counts.get(label, 0) + 1
    return counts


def lint_tags(tags: Iterable[TagInfo]) -> list[str]:
    issues: list[str] = []
    for info in tags:
        raw = info.raw
        if raw.strip() != raw:
            issues.append(f"Tag '{raw}' has leading/trailing whitespace")
        if raw.lower() != raw:
            issues.append(f"Tag '{raw}' should be lowercase")
        if any(char.isspace() for char in raw):
            issues.append(f"Tag '{raw}' contains whitespace")
    return sorted(set(issues))


def _iter_tags(payload: Any) -> Iterable[str]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "tags" and isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        yield item
                continue
            yield from _iter_tags(value)
        return
    if isinstance(payload, list):
        for item in payload:
            yield from _iter_tags(item)
