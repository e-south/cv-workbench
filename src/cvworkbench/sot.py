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
    "letters.yaml": "letters",
}

OPTIONAL_FILES = {
    "publications.yaml": "publications",
    "honors.yaml": "honors",
    "service.yaml": "service",
    "teaching.yaml": "teaching",
    "conferences.yaml": "conferences",
    "references.yaml": "references",
    "snippets.yaml": "snippets",
}


def load_sot(sot_path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}

    for filename, key in REQUIRED_FILES.items():
        path = sot_path / filename
        data[key] = _load_yaml(path)

    for filename, key in OPTIONAL_FILES.items():
        path = sot_path / filename
        if not path.exists():
            continue
        data[key] = _load_yaml(path)

    if "snippets" in data:
        data["snippets"] = _resolve_snippets(data["snippets"], sot_path)

    return data


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text())
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} must be a YAML mapping")

    return raw


def _resolve_snippets(snippet_data: dict[str, Any], sot_path: Path) -> dict[str, Any]:
    snippets = snippet_data.get("snippets")
    if not isinstance(snippets, list):
        raise ValueError("snippets.snippets must be a list")

    resolved: list[dict[str, Any]] = []
    for snippet in snippets:
        if not isinstance(snippet, dict):
            raise ValueError("snippets.snippets entries must be mappings")
        if "text" in snippet and "path" in snippet:
            raise ValueError("snippets cannot include both text and path")
        if "path" not in snippet:
            resolved.append(snippet)
            continue
        path_value = snippet.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            raise ValueError("snippet path must be a string")
        snippet_path = sot_path / path_value
        if not snippet_path.exists():
            raise ValueError(f"snippet path not found: {path_value}")
        content = snippet_path.read_text().strip()
        resolved.append({**snippet, "text": content, "path": None})

    return {"snippets": resolved}
