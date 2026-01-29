"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/sot.py

Loads Source of Truth (SoT) YAML data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REQUIRED_FILES = {
    "person.yaml": "person",
    "experience.yaml": "experience",
    "projects.yaml": "projects",
    "skills.yaml": "skills",
    "education.yaml": "education",
}


def load_sot(sot_path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}

    for filename, key in REQUIRED_FILES.items():
        path = sot_path / filename
        data[key] = _load_yaml(path)

    return data


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text())
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} must be a YAML mapping")

    return raw
