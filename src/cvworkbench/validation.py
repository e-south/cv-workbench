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

from cvworkbench.sot import REQUIRED_FILES
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

    if errors:
        return errors

    try:
        SotData.model_validate(payload)
    except ValidationError as exc:
        errors.extend(_format_errors(exc))

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
