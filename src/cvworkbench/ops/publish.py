"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/publish.py

Loads publish gating configuration for public outputs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


class PublishError(RuntimeError):
    pass


SUPPORTED_FORBIDDEN_CONTACT_FIELDS = frozenset({"phone"})


@dataclass(frozen=True)
class PublishConfig:
    variants: list[str]
    required_exclude_tags: list[str]
    forbidden_contact_fields: list[str]
    forbidden_sections: list[str]
    approved_visual_fingerprint_sha256: str


def load_publish_config(path: Path) -> PublishConfig:
    if not path.exists():
        raise PublishError(f"Publish config not found: {path}")

    raw = yaml.safe_load(path.read_text())
    if raw is None:
        raise PublishError("Publish config is empty")
    if not isinstance(raw, dict):
        raise PublishError("Publish config must be a YAML mapping")

    publish = raw.get("publish")
    if not isinstance(publish, dict):
        raise PublishError("Publish config must contain publish mapping")

    variants = _string_list(publish, "variants")
    required_exclude_tags = _string_list(publish, "required_exclude_tags")
    forbidden_contact_fields = _string_list(publish, "forbidden_contact_fields")
    forbidden_sections = _string_list(publish, "forbidden_sections")
    approved_visual_fingerprint_sha256 = publish.get("approved_visual_fingerprint_sha256")
    if not isinstance(approved_visual_fingerprint_sha256, str) or not re.fullmatch(
        r"[a-f0-9]{64}", approved_visual_fingerprint_sha256
    ):
        raise PublishError("Publish config must include a lowercase SHA-256 visual fingerprint")
    unsupported_contact_fields = sorted(
        set(forbidden_contact_fields) - SUPPORTED_FORBIDDEN_CONTACT_FIELDS
    )
    if unsupported_contact_fields:
        raise PublishError(
            "Publish config contains unsupported forbidden contact fields: "
            + ", ".join(unsupported_contact_fields)
        )

    return PublishConfig(
        variants=variants,
        required_exclude_tags=required_exclude_tags,
        forbidden_contact_fields=forbidden_contact_fields,
        forbidden_sections=forbidden_sections,
        approved_visual_fingerprint_sha256=approved_visual_fingerprint_sha256,
    )


def _string_list(data: dict[object, object], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise PublishError(f"Publish config must include publish.{key} list")

    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise PublishError(f"Publish {key} must contain non-empty strings")
        cleaned.append(item.strip())
    if len(cleaned) != len(set(cleaned)):
        raise PublishError(f"Publish {key} must not contain duplicates")
    return cleaned
