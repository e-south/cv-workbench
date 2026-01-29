"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/validation.py

Validates the Source of Truth (SoT) YAML files.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from cvworkbench.sot import OPTIONAL_FILES, REQUIRED_FILES
from cvworkbench.sot_schema import SotData


def validate_sot(sot_path: Path) -> list[str]:
    errors: list[str] = []

    if not sot_path.exists():
        return [f"SoT path does not exist: {sot_path}"]

    payload: dict[str, Any] = {}
    for filename, key in REQUIRED_FILES.items():
        path = sot_path / filename
        if not path.exists():
            errors.append(f"Missing required file: {filename}")
            continue
        data = _load_yaml_mapping(path, errors)
        if data is not None:
            payload[key] = data

    for filename, key in OPTIONAL_FILES.items():
        path = sot_path / filename
        if not path.exists():
            continue
        data = _load_yaml_mapping(path, errors)
        if data is not None:
            payload[key] = data

    if errors:
        return errors

    try:
        SotData.model_validate(payload)
    except ValidationError as exc:
        errors.extend(_format_errors(exc))
        return errors

    _validate_snippet_paths(payload, sot_path, errors)

    return errors


def _load_yaml_mapping(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if not path.exists():
        return None

    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        errors.append(f"Invalid YAML in {path.name}: {exc}")
        return None

    if raw is None:
        errors.append(f"{path.name} is empty")
        return None

    if not isinstance(raw, dict):
        errors.append(f"{path.name} must be a YAML mapping")
        return None

    return raw


def _format_errors(exc: ValidationError) -> list[str]:
    errors: list[str] = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", []))
        message = error.get("msg", "Invalid value")
        if loc:
            errors.append(f"{loc}: {message}")
        else:
            errors.append(message)
    return errors


def _validate_snippet_paths(payload: dict[str, Any], sot_path: Path, errors: list[str]) -> None:
    snippets_block = payload.get("snippets")
    if not isinstance(snippets_block, dict):
        return
    snippets = snippets_block.get("snippets")
    if not isinstance(snippets, list):
        return

    for snippet in snippets:
        if not isinstance(snippet, dict):
            continue
        path_value = snippet.get("path")
        if path_value is None:
            continue
        if not isinstance(path_value, str) or not path_value.strip():
            errors.append("snippets: snippet path must be a string")
            continue
        path = Path(path_value)
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"snippets: invalid snippet path: {path_value}")
            continue
        full_path = sot_path / path_value
        if not full_path.exists():
            snippet_id = snippet.get("id")
            label = f"snippets.{snippet_id}" if snippet_id else "snippets"
            errors.append(f"{label}: snippet path not found: {path_value}")
