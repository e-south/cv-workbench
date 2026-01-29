"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/resume.py

Builds JSON Resume payloads from Source of Truth data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_resume(sot: dict[str, Any]) -> dict[str, Any]:
    person = sot.get("person", {})
    basics = {
        "name": _text(person.get("name")),
        "label": _text(person.get("label")),
        "email": _text(person.get("email")),
        "summary": _text(person.get("summary")),
        "location": _build_location(person.get("location")),
        "profiles": _build_profiles(person.get("links")),
    }
    basics = {key: value for key, value in basics.items() if value}

    return {
        "basics": basics,
        "work": _build_work(sot.get("experience", {})),
        "projects": _build_projects(sot.get("projects", {})),
        "skills": _build_skills(sot.get("skills", {})),
        "education": _build_education(sot.get("education", {})),
    }


def write_resume(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, sort_keys=True)
    path.write_text(f"{data}\n")


def _build_location(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    location = {
        "city": _text(raw.get("city")),
        "region": _text(raw.get("region")),
        "countryCode": _text(raw.get("country")),
    }
    return {key: value for key, value in location.items() if value}


def _build_profiles(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    profiles: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        network = _text(item.get("label"))
        url = _text(item.get("url"))
        if not network or not url:
            continue
        profiles.append({"network": network, "url": url})
    return profiles


def _build_work(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    roles = raw.get("roles")
    if not isinstance(roles, list):
        return []

    work: list[dict[str, Any]] = []
    for role in roles:
        if not isinstance(role, dict):
            continue
        highlights = _build_highlights(role.get("bullets"))
        entry = {
            "name": _text(role.get("company")),
            "position": _text(role.get("title")),
            "location": _text(role.get("location")),
            "startDate": _date_text(role.get("start")),
            "endDate": _date_text(role.get("end")),
            "highlights": highlights,
        }
        work.append({key: value for key, value in entry.items() if value})
    return work


def _build_projects(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    projects = raw.get("projects")
    if not isinstance(projects, list):
        return []

    items: list[dict[str, Any]] = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        entry = {
            "name": _text(project.get("name")),
            "description": _text(project.get("summary")),
            "keywords": _text_list(project.get("tags")),
        }
        items.append({key: value for key, value in entry.items() if value})
    return items


def _build_skills(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    skills = raw.get("skills")
    if not isinstance(skills, list):
        return []

    items: list[dict[str, Any]] = []
    for skill in skills:
        if not isinstance(skill, dict):
            continue
        entry = {
            "name": _text(skill.get("name")),
            "keywords": _text_list(skill.get("keywords")),
        }
        items.append({key: value for key, value in entry.items() if value})
    return items


def _build_education(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    items = raw.get("education")
    if not isinstance(items, list):
        return []

    education: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        entry = {
            "institution": _text(item.get("institution")),
            "area": _text(item.get("area")),
            "studyType": _text(item.get("study_type")),
            "startDate": _date_text(item.get("start")),
            "endDate": _date_text(item.get("end")),
        }
        education.append({key: value for key, value in entry.items() if value})
    return education


def _build_highlights(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    highlights: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = _text(item.get("text"))
        if text:
            highlights.append(text)
    return highlights


def _text_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    values: list[str] = []
    for item in raw:
        text = _text(item)
        if text:
            values.append(text)
    return values


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _date_text(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return ""
