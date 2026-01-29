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
        "phone": _text(person.get("phone")),
        "summary": _text(person.get("summary")),
        "location": _build_location(person.get("location")),
        "profiles": _build_profiles(person.get("links")),
    }
    basics = {key: value for key, value in basics.items() if value}

    payload = {
        "basics": basics,
        "work": _build_work(sot.get("experience", {})),
        "projects": _build_projects(sot.get("projects", {})),
        "skills": _build_skills(sot.get("skills", {})),
        "education": _build_education(sot.get("education", {})),
        "publications": _build_publications(sot.get("publications", {})),
        "awards": _build_awards(sot.get("honors", {})),
        "volunteer": _build_volunteer(sot.get("service", {})),
        "references": _build_references(sot.get("references", {})),
    }

    meta = _build_meta(sot)
    if meta:
        payload["meta"] = meta

    return payload


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


def _build_publications(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    publications = raw.get("publications")
    if not isinstance(publications, list):
        return []

    items: list[dict[str, Any]] = []
    for publication in publications:
        if not isinstance(publication, dict):
            continue
        entry = {
            "name": _text(publication.get("title")),
            "publisher": _text(publication.get("venue")),
            "releaseDate": _date_text(publication.get("year")),
            "website": _text(publication.get("url")),
            "summary": _text(publication.get("notes")),
            "doi": _text(publication.get("doi")),
            "authors": _build_authors(publication.get("authors")),
            "tags": _text_list(publication.get("tags")),
        }
        items.append({key: value for key, value in entry.items() if value})
    return items


def _build_awards(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    honors = raw.get("honors")
    if not isinstance(honors, list):
        return []

    items: list[dict[str, Any]] = []
    for honor in honors:
        if not isinstance(honor, dict):
            continue
        entry = {
            "title": _text(honor.get("title")),
            "date": _date_text(honor.get("year")),
            "awarder": _text(honor.get("issuer")),
            "summary": _text(honor.get("summary")),
            "tags": _text_list(honor.get("tags")),
        }
        items.append({key: value for key, value in entry.items() if value})
    return items


def _build_volunteer(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    service = raw.get("service")
    if not isinstance(service, list):
        return []

    items: list[dict[str, Any]] = []
    for entry in service:
        if not isinstance(entry, dict):
            continue
        record = {
            "organization": _text(entry.get("organization")),
            "position": _text(entry.get("role")),
            "startDate": _date_text(entry.get("start")),
            "endDate": _date_text(entry.get("end")),
            "summary": _text(entry.get("summary")),
            "highlights": _text_list(entry.get("highlights")),
            "tags": _text_list(entry.get("tags")),
        }
        items.append({key: value for key, value in record.items() if value})
    return items


def _build_references(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    references = raw.get("references")
    if not isinstance(references, list):
        return []

    items: list[dict[str, Any]] = []
    for entry in references:
        if not isinstance(entry, dict):
            continue
        reference_text = _text(entry.get("notes"))
        if not reference_text:
            relationship = _text(entry.get("relationship"))
            email = _text(entry.get("email"))
            reference_bits = [bit for bit in [relationship, email] if bit]
            reference_text = " | ".join(reference_bits)
        record = {
            "name": _text(entry.get("name")),
            "reference": reference_text,
            "title": _text(entry.get("title")),
            "organization": _text(entry.get("organization")),
            "email": _text(entry.get("email")),
        }
        items.append({key: value for key, value in record.items() if value})
    return items


def _build_meta(sot: dict[str, Any]) -> dict[str, Any]:
    teaching = _build_teaching_meta(sot.get("teaching", {}))
    conferences = _build_conferences_meta(sot.get("conferences", {}))
    if not teaching and not conferences:
        return {}
    return {"cvworkbench": {"teaching": teaching, "conferences": conferences}}


def _build_teaching_meta(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    items = raw.get("teaching")
    if not isinstance(items, list):
        return []
    records: list[dict[str, Any]] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        record = {
            "course": _text(entry.get("course")),
            "role": _text(entry.get("role")),
            "term": _text(entry.get("term")),
            "enrollment": entry.get("enrollment") if isinstance(entry.get("enrollment"), int) else None,
            "evaluation": _text(entry.get("evaluation")),
            "summary": _text(entry.get("summary")),
            "tags": _text_list(entry.get("tags")),
        }
        records.append({key: value for key, value in record.items() if value})
    return records


def _build_conferences_meta(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    items = raw.get("conferences")
    if not isinstance(items, list):
        return []
    records: list[dict[str, Any]] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        record = {
            "title": _text(entry.get("title")),
            "event": _text(entry.get("event")),
            "year": _date_text(entry.get("year")),
            "location": _text(entry.get("location")),
            "presentation_type": _text(entry.get("presentation_type")),
            "notes": _text(entry.get("notes")),
            "tags": _text_list(entry.get("tags")),
        }
        records.append({key: value for key, value in record.items() if value})
    return records


def _build_authors(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    authors: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        record = {
            "name": _text(entry.get("name")),
            "roles": _text_list(entry.get("roles")),
            "affiliation": _text(entry.get("affiliation")),
            "orcid": _text(entry.get("orcid")),
        }
        record = {key: value for key, value in record.items() if value}
        if record:
            authors.append(record)
    return authors


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
