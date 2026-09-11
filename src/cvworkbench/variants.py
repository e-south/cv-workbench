"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/variants.py

Loads variant definitions that control document selection and outputs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cvworkbench.text import normalize_tags

CONTACT_FIELDS = ("label", "email", "phone", "location", "links")


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
    render_theme: str | None
    render_style_preset: str | None
    contact_fields: list[str] = field(default_factory=lambda: list(CONTACT_FIELDS))
    section_titles: dict[str, str] = field(default_factory=dict)
    render_page_break_before: list[str] = field(default_factory=list)
    render_entry_layout: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        validate_variant_id(self.id)
        _validate_entry_layout(self.render_entry_layout)
        starts = self.render_page_break_before
        if (
            not isinstance(starts, list)
            or any(
                not isinstance(value, str)
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]*", value) is None
                for value in starts
            )
            or len(set(starts)) != len(starts)
        ):
            raise ValueError(
                "Variant render.page_break_before must be a list of unique heading IDs"
            )
        if (
            not isinstance(self.output_name, str)
            or not self.output_name.strip()
            or self.output_name in {".", ".."}
            or re.search(r'[/\\<>:"|?*\x00-\x1f\x7f]', self.output_name)
        ):
            raise ValueError("Variant output_name must be a nonempty filename stem")


def validate_variant_id(variant_id: str) -> None:
    if (
        not isinstance(variant_id, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", variant_id) is None
    ):
        raise ValueError(
            "Variant id must start with a letter or number and contain only letters, numbers, '.', '_' or '-'"
        )


DEFAULT_ORDER = [
    "summary",
    "experience",
    "projects",
    "skills",
    "education",
    "publications",
    "conferences",
    "honors",
    "service",
    "teaching",
    "references",
]


@dataclass(frozen=True)
class VariantSnapshot:
    variant: Variant
    sha256: str


def load_variant(path: Path) -> Variant:
    return load_variant_snapshot(path).variant


def load_variant_snapshot(path: Path) -> VariantSnapshot:
    """Parse and fingerprint one captured variant definition."""
    content = path.read_bytes()
    variant = parse_variant_bytes(content)
    return VariantSnapshot(variant, hashlib.sha256(content).hexdigest())


def parse_variant_bytes(content: bytes) -> Variant:
    """Parse captured input without copying malformed private text into diagnostics."""
    try:
        payload = yaml.safe_load(content.decode("utf-8"))
    except (yaml.YAMLError, UnicodeError) as exc:
        raise ValueError("Variant is not valid UTF-8 YAML") from exc
    return parse_variant(payload)


def parse_variant(raw: object) -> Variant:
    """Validate one parsed definition without rereading its source file."""
    if raw is None:
        raise ValueError("Variant file is empty")
    if not isinstance(raw, dict):
        raise ValueError("Variant file must be a YAML mapping")

    variant_data = raw.get("variant")
    if not isinstance(variant_data, dict):
        raise ValueError("Variant file must contain a 'variant' mapping")

    variant_id = _require_str(variant_data, "id")
    outputs = _require_list(variant_data, "outputs")

    include_tags = normalize_tags(_string_list(variant_data.get("include_tags")))
    exclude_tags = normalize_tags(_string_list(variant_data.get("exclude_tags")))
    order = _string_list(variant_data.get("order"), default=DEFAULT_ORDER)
    max_bullets = _optional_int(variant_data.get("max_bullets_per_role"))
    output_name = variant_data.get("output_name")
    if output_name is None:
        output_name = "cv"
    document_type = _optional_str(variant_data.get("document_type"), default="resume")
    letter_id = _optional_str_or_none(variant_data.get("letter_id"))
    render_data = _optional_mapping(variant_data.get("render"))
    render_theme = _optional_str_or_none(render_data.get("theme")) if render_data else None
    render_style = _optional_str_or_none(render_data.get("style_preset")) if render_data else None
    contact_fields = _contact_fields(variant_data.get("contact_fields"))

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
        render_theme=render_theme,
        render_style_preset=render_style,
        contact_fields=contact_fields,
        section_titles=_section_titles(variant_data.get("section_titles")),
        render_page_break_before=render_data.get("page_break_before", []) if render_data else [],
        render_entry_layout=render_data.get("entry_layout", []) if render_data else [],
    )


def _validate_entry_layout(value: object) -> None:
    """Validate presentation references; selected-record existence is checked by Pandoc."""
    error = "Variant render.entry_layout must contain valid, nonoverlapping record references"
    if not isinstance(value, list):
        raise ValueError(error)
    consumed: set[str] = set()
    targets: set[str] = set()
    for rule in value:
        if not isinstance(rule, dict) or set(rule) - {
            "sources",
            "target",
            "placement",
            "label",
            "fields",
            "date_position",
            "group_by",
        }:
            raise ValueError(error)
        sources, target = rule.get("sources"), rule.get("target")
        if not isinstance(sources, list) or not sources:
            raise ValueError(error)
        for identity in [*sources, target]:
            if (
                not isinstance(identity, str)
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]*", identity) is None
            ):
                raise ValueError(error)
        if len(set(sources)) != len(sources) or consumed.intersection(sources):
            raise ValueError(error)
        consumed.update(sources)
        targets.add(target)
        if not isinstance(rule.get("placement"), str) or rule["placement"] not in {
            "details",
            "section",
            "shared_citation",
        }:
            raise ValueError(error)
        if rule["placement"] == "shared_citation" and (
            len(sources) < 2 or "fields" in rule or "label" in rule
        ):
            raise ValueError(error)
        fields = rule.get("fields")
        if "group_by" in rule and (
            rule["group_by"] != "series"
            or rule["placement"] != "section"
            or "date_position" in rule
            or (fields is not None and "heading" not in fields)
            or any(not source.startswith("conference-") for source in sources)
        ):
            raise ValueError(error)
        if "date_position" in rule and (
            rule["date_position"] != "right"
            or rule["placement"] != "section"
            or len(sources) != 1
            or (fields is not None and "date" not in fields)
        ):
            raise ValueError(error)
        if "fields" in rule and (
            not isinstance(fields, list)
            or not fields
            or any(
                not isinstance(name, str)
                or name
                not in {"heading", "role", "issuer", "location", "detail", "date", "summary"}
                for name in fields
            )
            or len(set(fields)) != len(fields)
        ):
            raise ValueError(error)
        label = rule.get("label")
        if "label" in rule and (
            rule["placement"] != "section"
            or not isinstance(label, str)
            or not label.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in label)
        ):
            raise ValueError(error)
    if consumed.intersection(targets):
        raise ValueError(error)


def _section_titles(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Variant section_titles must be a mapping")
    result = {}
    for section, title in value.items():
        if section not in DEFAULT_ORDER:
            raise ValueError("Variant section_titles contains an unknown section")
        if (
            not isinstance(title, str)
            or not title.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in title)
        ):
            raise ValueError("Variant section_titles values must be nonempty single-line text")
        result[section] = title.strip()
    return result


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


def _optional_mapping(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Variant field render must be a mapping")
    return value


def _contact_fields(value: object) -> list[str]:
    fields = _string_list(value, default=list(CONTACT_FIELDS))
    unknown = sorted(set(fields) - set(CONTACT_FIELDS))
    if unknown:
        raise ValueError(f"Unknown contact fields: {', '.join(unknown)}")
    if len(fields) != len(set(fields)):
        raise ValueError("Variant contact_fields must not contain duplicates")
    return fields


def _variants_dir(config_path: Path) -> Path:
    return config_path.parent / "variants"


def load_variants_from_config(config_path: Path) -> list[dict[str, Any]]:
    variants_dir = _variants_dir(config_path)
    if not variants_dir.exists():
        raise ValueError(f"Variants directory not found: {variants_dir}")
    variants: list[dict[str, Any]] = []
    for path in sorted(variants_dir.glob("*.yaml")):
        variant = load_variant(path)
        variants.append(
            {
                "id": variant.id,
                "document_type": variant.document_type,
                "outputs": variant.outputs,
                "include_tags": variant.include_tags,
                "exclude_tags": variant.exclude_tags,
                "letter_id": variant.letter_id,
                "render_theme": variant.render_theme,
                "render_style_preset": variant.render_style_preset,
                "render_page_break_before": list(variant.render_page_break_before),
                "render_entry_layout": list(variant.render_entry_layout),
                "max_bullets_per_role": variant.max_bullets_per_role,
                "section_titles": dict(variant.section_titles),
                "path": str(path),
            }
        )
    if not variants:
        raise ValueError("No variants found")
    return variants
