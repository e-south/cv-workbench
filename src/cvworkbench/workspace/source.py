"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/source.py

Inspect source files, sections, tags, and version metadata.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cvworkbench.config import (
    load_config,
    resolve_project_root,
)
from cvworkbench.inputs.sot import OPTIONAL_FILES, REQUIRED_FILES
from cvworkbench.inputs.sot_versions import (
    SotVersionError,
    resolve_versioned_root,
)
from cvworkbench.inputs.tags import extract_tags, tag_counts
from cvworkbench.ops.sot_versions import (
    SotPackError,
    list_versions,
)


def inspect_source(sot_path: Path):
    from cvworkbench.inputs.validation import inspect_sot

    return inspect_sot(sot_path)


def configured_sot_path(config_path: Path) -> str | None:
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError):
        return None
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        return None
    value = paths.get("sot")
    if not isinstance(value, str) or not value.strip():
        return None
    return str((config_path.parent / value.strip()).resolve())


def sample_sot_path(config_path: Path) -> Path | None:
    sample_path = resolve_project_root(config_path) / "sot.sample"
    if sample_path.exists():
        return sample_path
    return None


def is_local_scaffold_sot(configured_sot_path: str | None) -> bool:
    if not configured_sot_path:
        return False
    parts = Path(configured_sot_path).parts
    return len(parts) >= 2 and parts[-2:] == ("local", "sot")


def build_sot_details(resolved_sot: Path, payload: dict[str, Any]) -> dict[str, Any]:
    files = _collect_sot_files(resolved_sot)
    files_summary = _files_summary_line(files)
    sections = _summarize_sot_sections(payload)
    sections_summary = _summarize_sections_line(sections)
    tags = extract_tags(payload)
    counts = tag_counts(tags)
    tags_top = top_tags(counts)
    tags_summary = tags_summary_line(tags_top)
    return {
        "files": files,
        "files_summary": files_summary,
        "sections": sections,
        "sections_summary": sections_summary,
        "tags_top": tags_top,
        "tags_summary": tags_summary,
    }


def build_versions_info(resolved_sot: Path) -> tuple[dict[str, Any] | None, str, str | None]:
    try:
        version_root = resolve_versioned_root(resolved_sot)
    except SotVersionError:
        return None, "", None
    try:
        version_state = list_versions(version_root)
    except SotPackError as exc:
        return None, "", str(exc)
    versions_info = {
        "root": str(version_state.root),
        "active": version_state.active,
        "versions": version_state.versions,
    }
    versions_summary = (
        f"root={version_state.root} active={version_state.active} "
        f"count={len(version_state.versions)}"
    )
    return versions_info, versions_summary, None


def _format_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _collect_sot_files(sot_path: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for filename in list(REQUIRED_FILES.keys()) + list(OPTIONAL_FILES.keys()):
        path = sot_path / filename
        if path.exists():
            files.append(
                {
                    "name": filename,
                    "path": str(path),
                    "status": "present",
                    "modified_at": _format_timestamp(path.stat().st_mtime),
                }
            )
        else:
            files.append(
                {
                    "name": filename,
                    "path": str(path),
                    "status": "missing",
                    "modified_at": None,
                }
            )
    return files


def _files_summary_line(files: list[dict[str, Any]]) -> str:
    present = [item["name"] for item in files if item["status"] == "present"]
    missing = [item["name"] for item in files if item["status"] == "missing"]
    parts: list[str] = []
    if present:
        parts.append("present: " + ", ".join(present))
    if missing:
        parts.append("missing: " + ", ".join(missing))
    return "; ".join(parts) if parts else "none"


def _count_list_section(payload: dict[str, Any], section: str, key: str) -> int:
    data = payload.get(section)
    if not isinstance(data, dict):
        return 0
    values = data.get(key)
    if not isinstance(values, list):
        return 0
    return len(values)


def _summarize_sot_sections(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    experience = payload.get("experience")
    roles_count = 0
    bullets_count = 0
    if isinstance(experience, dict):
        roles = experience.get("roles")
        if isinstance(roles, list):
            roles_count = len(roles)
            for role in roles:
                if not isinstance(role, dict):
                    continue
                bullets = role.get("bullets")
                if isinstance(bullets, list):
                    bullets_count += len(bullets)
    summary["experience"] = {"roles": roles_count, "bullets": bullets_count}
    summary["projects"] = {"count": _count_list_section(payload, "projects", "projects")}
    summary["skills"] = {"count": _count_list_section(payload, "skills", "skills")}
    summary["education"] = {"count": _count_list_section(payload, "education", "education")}
    summary["publications"] = {
        "count": _count_list_section(payload, "publications", "publications")
    }
    summary["honors"] = {"count": _count_list_section(payload, "honors", "honors")}
    summary["service"] = {"count": _count_list_section(payload, "service", "service")}
    summary["teaching"] = {"count": _count_list_section(payload, "teaching", "teaching")}
    summary["conferences"] = {"count": _count_list_section(payload, "conferences", "conferences")}
    summary["references"] = {"count": _count_list_section(payload, "references", "references")}
    letters_count = 0
    letter_sections = 0
    letters = payload.get("letters")
    if isinstance(letters, dict):
        letter_list = letters.get("letters")
        if isinstance(letter_list, list):
            letters_count = len(letter_list)
            for letter in letter_list:
                if not isinstance(letter, dict):
                    continue
                sections = letter.get("sections")
                if isinstance(sections, list):
                    letter_sections += len(sections)
    summary["letters"] = {"letters": letters_count, "sections": letter_sections}
    snippets_count = 0
    snippets = payload.get("snippets")
    if isinstance(snippets, dict):
        snippet_list = snippets.get("snippets")
        if isinstance(snippet_list, list):
            snippets_count = len(snippet_list)
    summary["snippets"] = {"count": snippets_count}
    return summary


def _summarize_sections_line(summary: dict[str, Any]) -> str:
    parts: list[str] = []
    experience = summary.get("experience", {})
    parts.append(
        f"experience roles={experience.get('roles', 0)} bullets={experience.get('bullets', 0)}"
    )
    for key in [
        "projects",
        "skills",
        "education",
        "publications",
        "conferences",
        "honors",
        "service",
        "teaching",
        "references",
    ]:
        count = summary.get(key, {}).get("count", 0)
        parts.append(f"{key}={count}")
    letters = summary.get("letters", {})
    parts.append(f"letters={letters.get('letters', 0)} sections={letters.get('sections', 0)}")
    snippets = summary.get("snippets", {})
    parts.append(f"snippets={snippets.get('count', 0)}")
    return "; ".join(parts)


def top_tags(counts: dict[str, int], limit: int = 10) -> list[dict[str, Any]]:
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"tag": tag, "count": count} for tag, count in ordered[:limit]]


def tags_summary_line(tags: list[dict[str, Any]]) -> str:
    if not tags:
        return "none"
    return ", ".join([f"{item['tag']}({item['count']})" for item in tags])
