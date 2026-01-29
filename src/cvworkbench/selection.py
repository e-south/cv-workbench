"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/selection.py

Builds selection metadata for explainable variant filtering.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from cvworkbench.text import slugify, tag_classes
from cvworkbench.variants import Variant


def build_selection(sot: dict[str, Any], variant: Variant) -> dict[str, Any]:
    include_set = set(variant.include_tags)
    exclude_set = set(variant.exclude_tags)
    items: list[dict[str, Any]] = []

    _append_bullets(items, sot, include_set, exclude_set, variant.max_bullets_per_role)
    _append_section_items(items, sot, include_set, exclude_set)

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "variant": variant.id,
        "max_bullets_per_role": variant.max_bullets_per_role,
        "items": items,
    }


def _append_bullets(
    items: list[dict[str, Any]],
    sot: dict[str, Any],
    include_set: set[str],
    exclude_set: set[str],
    max_bullets: int | None,
) -> None:
    experience = sot.get("experience", {})
    roles = experience.get("roles")
    if not isinstance(roles, list):
        return

    for role in roles:
        if not isinstance(role, dict):
            continue
        role_id = slugify(role.get("id", ""))
        bullets = role.get("bullets")
        if not isinstance(bullets, list):
            continue

        selected_count = 0
        for bullet in bullets:
            if not isinstance(bullet, dict):
                continue
            bullet_id = slugify(bullet.get("id", ""))
            bullet_text = bullet.get("text")
            tags = _tag_classes(bullet.get("tags"))
            included, reasons = _evaluate_tags(tags, include_set, exclude_set)
            if included and max_bullets is not None:
                selected_count += 1
                if selected_count > max_bullets:
                    included = False
                    reasons.append("max_bullets_per_role")
            items.append(
                {
                    "id": bullet_id,
                    "type": "bullet",
                    "role_id": role_id,
                    "text": bullet_text if isinstance(bullet_text, str) else None,
                    "tags": sorted(tags),
                    "included": included,
                    "reasons": reasons,
                }
            )


def _append_section_items(
    items: list[dict[str, Any]],
    sot: dict[str, Any],
    include_set: set[str],
    exclude_set: set[str],
) -> None:
    section_map = [
        ("projects", "projects"),
        ("education", "education"),
        ("publications", "publications"),
        ("conferences", "conferences"),
        ("honors", "honors"),
        ("service", "service"),
        ("teaching", "teaching"),
        ("references", "references"),
    ]
    for section_key, list_key in section_map:
        section = sot.get(section_key, {})
        items_list = section.get(list_key)
        if not isinstance(items_list, list):
            continue
        for entry in items_list:
            if not isinstance(entry, dict):
                continue
            entry_id = slugify(entry.get("id", ""))
            label = _entry_label(entry)
            tags = _tag_classes(entry.get("tags"))
            included, reasons = _evaluate_tags(tags, include_set, exclude_set)
            items.append(
                {
                    "id": entry_id,
                    "type": "section",
                    "section": section_key,
                    "label": label,
                    "tags": sorted(tags),
                    "included": included,
                    "reasons": reasons,
                }
            )


def _evaluate_tags(
    tags: set[str],
    include_set: set[str],
    exclude_set: set[str],
) -> tuple[bool, list[str]]:
    if tags & exclude_set:
        return False, [f"exclude_tag:{sorted(tags & exclude_set)[0]}"]
    if include_set and not tags & include_set:
        return False, ["missing_include"]
    return True, []


def _tag_classes(raw_tags: Any) -> set[str]:
    if not isinstance(raw_tags, list):
        return set()
    classes: set[str] = set()
    for tag in raw_tags:
        if not isinstance(tag, str):
            continue
        for klass in tag_classes(tag):
            classes.add(klass)
    return classes


def _entry_label(entry: dict[str, Any]) -> str | None:
    for key in ("name", "institution", "title", "organization", "issuer"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
