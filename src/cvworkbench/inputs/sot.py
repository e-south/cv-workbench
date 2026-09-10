"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/inputs/sot.py

Loads Source of Truth (SoT) YAML data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
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


@dataclass(frozen=True)
class SotSnapshot:
    data: dict[str, Any] = field(repr=False)
    sot_hashes: Mapping[str, str]
    snippet_hashes: Mapping[str, str]


def load_sot(sot_path: Path) -> dict[str, Any]:
    return load_sot_snapshot(sot_path).data


def load_sot_snapshot(sot_path: Path) -> SotSnapshot:
    """Load source content and fingerprint the same bytes used to parse it."""
    data: dict[str, Any] = {}
    hashes: dict[str, str] = {}

    for filename, key in REQUIRED_FILES.items():
        path = sot_path / filename
        content = path.read_bytes()
        data[key] = _load_yaml(content, path)
        hashes[filename] = hashlib.sha256(content).hexdigest()

    for filename, key in OPTIONAL_FILES.items():
        path = sot_path / filename
        if not path.exists():
            continue
        content = path.read_bytes()
        data[key] = _load_yaml(content, path)
        hashes[filename] = hashlib.sha256(content).hexdigest()

    snippet_hashes: dict[str, str] = {}
    if "snippets" in data:
        data["snippets"], snippet_hashes = _resolve_snippets(data["snippets"], sot_path)

    return SotSnapshot(data, MappingProxyType(hashes), MappingProxyType(snippet_hashes))


def _load_yaml(content: bytes, path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(content.decode("utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} must be a YAML mapping")

    return raw


def _resolve_snippets(
    snippet_data: dict[str, Any], sot_path: Path
) -> tuple[dict[str, Any], dict[str, str]]:
    snippets = snippet_data.get("snippets")
    if not isinstance(snippets, list):
        raise ValueError("snippets.snippets must be a list")

    resolved: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    contents: dict[str, str] = {}
    for snippet in snippets:
        if not isinstance(snippet, dict):
            raise ValueError("snippets.snippets entries must be mappings")
        if "text" in snippet and "path" in snippet:
            raise ValueError("snippets cannot include both text and path")
        if "path" not in snippet:
            text = snippet.get("text")
            if isinstance(text, str) and text.strip():
                snippet_id = snippet.get("id") or "snippet"
                hashes[f"inline:{snippet_id}"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
            resolved.append(snippet)
            continue
        path_value = snippet.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            raise ValueError("snippet path must be a string")
        if path_value not in contents:
            snippet_path = sot_path / path_value
            if not snippet_path.exists():
                raise ValueError(f"snippet path not found: {path_value}")
            content = snippet_path.read_bytes()
            hashes[path_value] = hashlib.sha256(content).hexdigest()
            contents[path_value] = (
                content.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").strip()
            )
        resolved.append({**snippet, "text": contents[path_value], "path": None})

    return {"snippets": resolved}, hashes
