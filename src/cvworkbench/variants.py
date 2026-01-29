"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/variants.py

Loads variant definitions that control document selection and outputs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Variant:
    id: str
    include_tags: list[str]
    exclude_tags: list[str]
    max_bullets_per_role: int | None
    order: list[str]
    outputs: list[str]
    output_name: str
    document_type: str
    letter_id: str | None


DEFAULT_ORDER = ["summary", "experience", "projects", "skills", "education"]


def load_variant(path: Path) -> Variant:
    raw = yaml.safe_load(path.read_text())
    if raw is None:
        raise ValueError("Variant file is empty")
    if not isinstance(raw, dict):
        raise ValueError("Variant file must be a YAML mapping")

    variant_data = raw.get("variant")
    if not isinstance(variant_data, dict):
        raise ValueError("Variant file must contain a 'variant' mapping")

    variant_id = _require_str(variant_data, "id")
    outputs = _require_list(variant_data, "outputs")

    include_tags = _string_list(variant_data.get("include_tags"))
    exclude_tags = _string_list(variant_data.get("exclude_tags"))
    order = _string_list(variant_data.get("order"), default=DEFAULT_ORDER)
    max_bullets = _optional_int(variant_data.get("max_bullets_per_role"))
    output_name = _optional_str(variant_data.get("output_name"), default="cv")
    document_type = _optional_str(variant_data.get("document_type"), default="resume")
    letter_id = _optional_str_or_none(variant_data.get("letter_id"))

    return Variant(
        id=variant_id,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
        max_bullets_per_role=max_bullets,
        order=order,
        outputs=outputs,
        output_name=output_name,
        document_type=document_type,
        letter_id=letter_id,
    )


def _require_str(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Variant field '{key}' is required")
    return value


def _require_list(data: dict[str, object], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"Variant field '{key}' is required")
    return _string_list(value)


def _string_list(value: object, default: list[str] | None = None) -> list[str]:
    if value is None:
        return list(default or [])
    if not isinstance(value, list):
        raise ValueError("Variant list fields must be lists")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("Variant list fields must contain strings")
        items.append(item)
    return items


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError("Variant field max_bullets_per_role must be an integer")
    return value


def _optional_str(value: object, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        return default
    return value


def _optional_str_or_none(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value
