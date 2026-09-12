"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/text.py

Provides shared string normalization helpers.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import re
from collections.abc import Sequence


def title_italic_spans(title: str, phrases: Sequence[str]) -> list[tuple[int, int]]:
    """Locate explicit literal phrases; reject stale or overlapping formatting."""
    spans: list[tuple[int, int]] = []
    for phrase in phrases:
        if not phrase or phrase not in title:
            raise ValueError("title italics must match nonempty text in the title")
        spans.extend(
            (match.start(), match.start() + len(phrase))
            for match in re.finditer(f"(?={re.escape(phrase)})", title)
        )
    spans.sort()
    if any(left[1] > right[0] for left, right in zip(spans, spans[1:], strict=False)):
        raise ValueError("title italics must not overlap or repeat")
    return spans


def slugify(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    cleaned: list[str] = []
    for char in value.strip().lower():
        if char.isalnum():
            cleaned.append(char)
        else:
            cleaned.append("-")
    slug = "".join(cleaned)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def normalize_tag(tag: str) -> str:
    return slugify(tag)


def tag_classes(tag: str) -> list[str]:
    full = normalize_tag(tag)
    if not full:
        return []
    classes = [full]
    if ":" in tag:
        namespace = normalize_tag(tag.split(":", 1)[0])
        if namespace and namespace not in classes:
            classes.insert(0, namespace)
    return classes


def normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        slug = normalize_tag(tag)
        if not slug or slug in seen:
            continue
        normalized.append(slug)
        seen.add(slug)
    return normalized
