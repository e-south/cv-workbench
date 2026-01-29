"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/publish.py

Loads publish gating configuration for public outputs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class PublishError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublishConfig:
    variants: list[str]


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

    variants = publish.get("variants")
    if not isinstance(variants, list) or not variants:
        raise PublishError("Publish config must include publish.variants list")

    cleaned: list[str] = []
    for item in variants:
        if not isinstance(item, str) or not item.strip():
            raise PublishError("Publish variants must be non-empty strings")
        cleaned.append(item.strip())

    return PublishConfig(variants=cleaned)
