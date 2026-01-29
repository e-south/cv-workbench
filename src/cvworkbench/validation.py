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

REQUIRED_FILES = {
    "person.yaml": "person",
    "experience.yaml": "experience",
    "projects.yaml": "projects",
    "skills.yaml": "skills",
    "education.yaml": "education",
}


def validate_sot(sot_path: Path) -> list[str]:
    errors: list[str] = []

    if not sot_path.exists():
        return [f"SoT path does not exist: {sot_path}"]

    for filename in REQUIRED_FILES:
        if not (sot_path / filename).exists():
            errors.append(f"Missing required file: {filename}")

    person = _load_yaml_mapping(sot_path / "person.yaml", errors)
    if person is not None:
        _validate_person(person, errors)

    experience = _load_yaml_mapping(sot_path / "experience.yaml", errors)
    if experience is not None:
        _validate_experience(experience, errors)

    projects = _load_yaml_mapping(sot_path / "projects.yaml", errors)
    if projects is not None:
        _validate_projects(projects, errors)

    skills = _load_yaml_mapping(sot_path / "skills.yaml", errors)
    if skills is not None:
        _validate_skills(skills, errors)

    education = _load_yaml_mapping(sot_path / "education.yaml", errors)
    if education is not None:
        _validate_education(education, errors)

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


def _validate_person(person: dict[str, Any], errors: list[str]) -> None:
    _require_str(person, "id", "person", errors)
    _require_str(person, "name", "person", errors)


def _validate_experience(experience: dict[str, Any], errors: list[str]) -> None:
    roles = _require_list(experience, "roles", "experience", errors)
    for index, role in enumerate(roles):
        if not isinstance(role, dict):
            errors.append(f"experience.roles[{index}] must be a mapping")
            continue
        role_path = f"experience.roles[{index}]"
        _require_str(role, "id", role_path, errors)
        _require_str(role, "company", role_path, errors)
        _require_str(role, "title", role_path, errors)
        _require_str(role, "start", role_path, errors)
        bullets = _require_list(role, "bullets", role_path, errors)
        for bullet_index, bullet in enumerate(bullets):
            if not isinstance(bullet, dict):
                errors.append(f"{role_path}.bullets[{bullet_index}] must be a mapping")
                continue
            bullet_path = f"{role_path}.bullets[{bullet_index}]"
            _require_str(bullet, "id", bullet_path, errors)
            _require_str(bullet, "text", bullet_path, errors)
            _require_str_list(bullet, "tags", bullet_path, errors)


def _validate_projects(projects: dict[str, Any], errors: list[str]) -> None:
    items = _require_list(projects, "projects", "projects", errors)
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"projects.projects[{index}] must be a mapping")
            continue
        item_path = f"projects.projects[{index}]"
        _require_str(item, "id", item_path, errors)
        _require_str(item, "name", item_path, errors)
        _require_str(item, "summary", item_path, errors)
        _require_str_list(item, "tags", item_path, errors)


def _validate_skills(skills: dict[str, Any], errors: list[str]) -> None:
    items = _require_list(skills, "skills", "skills", errors)
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"skills.skills[{index}] must be a mapping")
            continue
        item_path = f"skills.skills[{index}]"
        _require_str(item, "id", item_path, errors)
        _require_str(item, "name", item_path, errors)
        _require_str_list(item, "keywords", item_path, errors)


def _validate_education(education: dict[str, Any], errors: list[str]) -> None:
    items = _require_list(education, "education", "education", errors)
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"education.education[{index}] must be a mapping")
            continue
        item_path = f"education.education[{index}]"
        _require_str(item, "id", item_path, errors)
        _require_str(item, "institution", item_path, errors)
        _require_str(item, "area", item_path, errors)


def _require_list(
    mapping: dict[str, Any],
    key: str,
    path: str,
    errors: list[str],
) -> list[Any]:
    value = mapping.get(key)
    if value is None:
        errors.append(f"{path}.{key} is required")
        return []
    if not isinstance(value, list):
        errors.append(f"{path}.{key} must be a list")
        return []
    return value


def _require_str(
    mapping: dict[str, Any],
    key: str,
    path: str,
    errors: list[str],
) -> None:
    value = mapping.get(key)
    if value is None:
        errors.append(f"{path}.{key} is required")
        return
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{key} must be a non-empty string")


def _require_str_list(
    mapping: dict[str, Any],
    key: str,
    path: str,
    errors: list[str],
) -> None:
    value = mapping.get(key)
    if value is None:
        errors.append(f"{path}.{key} is required")
        return
    if not isinstance(value, list) or not value:
        errors.append(f"{path}.{key} must be a non-empty list")
        return
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{path}.{key}[{index}] must be a non-empty string")
