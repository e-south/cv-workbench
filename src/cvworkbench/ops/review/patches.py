"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/review/patches.py

Interprets supported Markdown edits as compare-and-set content patches.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path
from typing import Any

import yaml

from cvworkbench.build.selection import build_selection
from cvworkbench.inputs.sot import load_sot
from cvworkbench.ops.projects import ProjectError, ProjectPatch, compile_project_patch
from cvworkbench.text import slugify
from cvworkbench.variants import Variant


def _diff_text(canonical_path: Path, imported_markdown: str) -> str:
    before = canonical_path.read_text().splitlines()
    after = imported_markdown.splitlines()
    diff = unified_diff(before, after, fromfile="canonical.md", tofile="imported.md", lineterm="")
    return "\n".join(diff) + ("\n" if before or after else "")


@dataclass(frozen=True)
class _MarkdownToken:
    kind: str
    section: str | None
    heading: str | None
    text: str


@dataclass(frozen=True)
class _ExperienceBulletRef:
    role_id: str
    bullet_id: str
    heading: str
    source_text: str
    rendered_text: str


@dataclass(frozen=True)
class _ProjectSummaryRef:
    project_id: str
    heading: str
    source_text: str
    rendered_text: str


def build_import_patch(
    *,
    canonical_path: Path,
    imported_markdown: str,
    sot_path: Path,
    variant: Variant,
    project_patch: ProjectPatch | None,
) -> tuple[str, str, str, list[str]]:
    supported = _build_supported_project_patch(
        canonical_markdown=canonical_path.read_text(),
        imported_markdown=imported_markdown,
        sot_path=sot_path,
        variant=variant,
        project_patch=project_patch,
    )
    if supported is not None:
        apply_status = "ready" if len(supported.operations) > 0 else "ready_no_changes"
        note_lines = (
            [
                "This draft matched supported experience bullet or project summary text edits.",
                "patch.yaml records compare-and-set project-ops targeting SoT files.",
            ]
            if len(supported.operations) > 0
            else [
                "This draft normalized to a supported project-ops patch with no SoT mutations.",
                "patch.yaml is a verified no-op after markdown normalization.",
            ]
        )
        return (
            "patch.yaml",
            yaml.safe_dump(
                {
                    "patch": {
                        "format": supported.format,
                        "operations": list(supported.operations),
                    }
                },
                sort_keys=False,
            ),
            apply_status,
            note_lines,
        )
    return (
        "patch.diff",
        _diff_text(canonical_path, imported_markdown),
        "review_diff_only",
        [
            "This draft compares reviewed DOCX content against canonical.md.",
            "It is not directly applyable to SoT.",
            "Review the diff and author a real SoT patch manually.",
        ],
    )


def _build_supported_project_patch(
    *,
    canonical_markdown: str,
    imported_markdown: str,
    sot_path: Path,
    variant: Variant,
    project_patch: ProjectPatch | None,
) -> ProjectPatch | None:
    if variant.document_type != "resume":
        return None

    canonical_tokens = _coalesce_noneditable_text_tokens(_tokenize_markdown(canonical_markdown))
    imported_tokens = _coalesce_noneditable_text_tokens(_tokenize_markdown(imported_markdown))
    if len(canonical_tokens) != len(imported_tokens):
        return None

    for canonical_token, imported_token in zip(canonical_tokens, imported_tokens, strict=False):
        if (
            canonical_token.kind != imported_token.kind
            or canonical_token.section != imported_token.section
            or canonical_token.heading != imported_token.heading
        ):
            return None
        if canonical_token.text == imported_token.text:
            continue
        if _normalize_noneditable_token_text(
            canonical_token.text
        ) == _normalize_noneditable_token_text(imported_token.text):
            continue
        if canonical_token.kind == "bullet" and canonical_token.section == "Experience":
            continue
        if (
            canonical_token.kind == "text"
            and canonical_token.section == "Projects"
            and canonical_token.heading
        ):
            continue
        return None

    sot = load_sot(sot_path)
    bullet_refs = _selected_experience_bullets(sot, variant, project_patch=project_patch)
    project_refs = _selected_project_summaries(sot, variant=variant, project_patch=project_patch)
    if bullet_refs is None or project_refs is None:
        return None
    canonical_experience = [
        token
        for token in canonical_tokens
        if token.kind == "bullet" and token.section == "Experience"
    ]
    imported_experience = [
        token
        for token in imported_tokens
        if token.kind == "bullet" and token.section == "Experience"
    ]
    canonical_projects = [
        token
        for token in canonical_tokens
        if token.kind == "text" and token.section == "Projects" and token.heading
    ]
    imported_projects = [
        token
        for token in imported_tokens
        if token.kind == "text" and token.section == "Projects" and token.heading
    ]
    if len(canonical_experience) != len(imported_experience):
        return None
    if len(canonical_projects) != len(imported_projects):
        return None
    if canonical_experience:
        if len(canonical_experience) != len(bullet_refs):
            return None
        for canonical_token, ref in zip(canonical_experience, bullet_refs, strict=False):
            if canonical_token.heading != ref.heading or canonical_token.text != ref.rendered_text:
                return None
    if canonical_projects:
        if len(canonical_projects) != len(project_refs):
            return None
        for canonical_token, ref in zip(canonical_projects, project_refs, strict=False):
            if canonical_token.heading != ref.heading or canonical_token.text != ref.rendered_text:
                return None

    operations: list[dict[str, str]] = []
    for canonical_token, imported_token, ref in zip(
        canonical_experience,
        imported_experience,
        bullet_refs,
        strict=False,
    ):
        if canonical_token.text == imported_token.text:
            continue
        operations.append(
            {
                "op": "replace-experience-bullet",
                "role_id": ref.role_id,
                "bullet_id": ref.bullet_id,
                "old_text": ref.source_text,
                "new_text": imported_token.text,
            }
        )
    for canonical_token, imported_token, ref in zip(
        canonical_projects, imported_projects, project_refs, strict=False
    ):
        if canonical_token.text == imported_token.text:
            continue
        operations.append(
            {
                "op": "replace-project-summary",
                "project_id": ref.project_id,
                "old_text": ref.source_text,
                "new_text": imported_token.text,
            }
        )

    patch = ProjectPatch(format="project-ops", diff="", operations=tuple(operations))
    try:
        compile_project_patch(patch=patch, sot_path=sot_path)
    except ProjectError:
        return None
    return patch


def _selected_experience_bullets(
    sot: dict[str, Any],
    variant: Variant,
    *,
    project_patch: ProjectPatch | None,
) -> list[_ExperienceBulletRef] | None:
    selection = build_selection(sot, variant)
    included = {
        (str(item.get("role_id")), str(item.get("id")))
        for item in selection.get("items", [])
        if isinstance(item, dict) and item.get("type") == "bullet" and item.get("included") is True
    }
    refs: list[_ExperienceBulletRef] = []
    experience = sot.get("experience", {})
    roles = experience.get("roles")
    if not isinstance(roles, list):
        return refs
    for role in roles:
        if not isinstance(role, dict):
            continue
        role_id = slugify(role.get("id", ""))
        heading = " - ".join(
            part
            for part in [str(role.get("title", "")).strip(), str(role.get("company", "")).strip()]
            if part
        )
        bullets = role.get("bullets")
        if not isinstance(bullets, list):
            continue
        for bullet in bullets:
            if not isinstance(bullet, dict):
                continue
            bullet_id = slugify(bullet.get("id", ""))
            if (role_id, bullet_id) not in included:
                continue
            text = bullet.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            refs.append(
                _ExperienceBulletRef(
                    role_id=role_id,
                    bullet_id=bullet_id,
                    heading=_normalize_markdown_text(heading),
                    source_text=text.strip(),
                    rendered_text=_normalize_markdown_text(text),
                )
            )
    return _apply_project_patch_to_bullet_refs(refs, project_patch)


def _selected_project_summaries(
    sot: dict[str, Any],
    *,
    variant: Variant,
    project_patch: ProjectPatch | None,
) -> list[_ProjectSummaryRef] | None:
    selection = build_selection(sot, variant)
    included = {
        str(item.get("id"))
        for item in selection.get("items", [])
        if isinstance(item, dict)
        and item.get("type") == "section"
        and item.get("section") == "projects"
        and item.get("included") is True
    }
    refs: list[_ProjectSummaryRef] = []
    projects = sot.get("projects", {})
    items = projects.get("projects")
    if not isinstance(items, list):
        return refs
    for item in items:
        if not isinstance(item, dict):
            continue
        project_id = slugify(item.get("id", ""))
        if project_id not in included:
            continue
        heading = str(item.get("name", "")).strip()
        summary = item.get("summary")
        if not project_id or not heading or not isinstance(summary, str) or not summary.strip():
            continue
        refs.append(
            _ProjectSummaryRef(
                project_id=project_id,
                heading=_normalize_markdown_text(heading),
                source_text=summary.strip(),
                rendered_text=_normalize_markdown_text(summary),
            )
        )
    return _apply_project_patch_to_project_refs(refs, project_patch)


def _tokenize_markdown(markdown: str) -> list[_MarkdownToken]:
    tokens: list[_MarkdownToken] = []
    section: str | None = None
    heading: str | None = None
    paragraph_kind: str | None = None
    paragraph_section: str | None = None
    paragraph_heading: str | None = None
    paragraph_parts: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_kind, paragraph_section, paragraph_heading, paragraph_parts
        if paragraph_kind is None:
            return
        text = _normalize_markdown_text(" ".join(paragraph_parts))
        if text:
            tokens.append(
                _MarkdownToken(
                    kind=paragraph_kind,
                    section=paragraph_section,
                    heading=paragraph_heading,
                    text=text,
                )
            )
        paragraph_kind = None
        paragraph_section = None
        paragraph_heading = None
        paragraph_parts = []

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line or line == ":::" or line.startswith("::: "):
            flush_paragraph()
            continue
        if line.startswith("## "):
            flush_paragraph()
            section = _normalize_markdown_text(line[3:])
            heading = None
            tokens.append(
                _MarkdownToken(kind="section", section=section, heading=None, text=section)
            )
            continue
        if line.startswith("### "):
            flush_paragraph()
            heading = _normalize_markdown_text(line[4:])
            tokens.append(
                _MarkdownToken(kind="heading", section=section, heading=heading, text=heading)
            )
            continue
        if line.startswith("- "):
            flush_paragraph()
            paragraph_kind = "bullet"
            paragraph_section = section
            paragraph_heading = heading
            paragraph_parts = [line[2:].strip()]
            continue
        if paragraph_kind is None:
            paragraph_kind = "text"
            paragraph_section = section
            paragraph_heading = heading
            paragraph_parts = [line]
            continue
        paragraph_parts.append(line)
    flush_paragraph()
    return tokens


def _coalesce_noneditable_text_tokens(tokens: list[_MarkdownToken]) -> list[_MarkdownToken]:
    merged: list[_MarkdownToken] = []
    for token in tokens:
        if (
            merged
            and token.kind == "text"
            and merged[-1].kind == "text"
            and token.section == merged[-1].section
            and token.heading == merged[-1].heading
            and not (token.section == "Projects" and token.heading)
        ):
            previous = merged[-1]
            merged[-1] = _MarkdownToken(
                kind=previous.kind,
                section=previous.section,
                heading=previous.heading,
                text=_normalize_markdown_text(f"{previous.text} {token.text}"),
            )
            continue
        merged.append(token)
    return merged


def _normalize_markdown_text(text: str) -> str:
    normalized = text.strip().replace("\xa0", " ")
    normalized = re.sub(r"(?<=\d)--(?=\d)", "–", normalized)
    normalized = re.sub(r"(?<=\S)\s+---\s+(?=\S)", " — ", normalized)
    normalized = normalized.replace(r"\|", "|")
    normalized = re.sub(r"\[([^\]]+)\]\{[^{}]*\}", r"\1", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _normalize_noneditable_token_text(text: str) -> str:
    return re.sub(r"(?<=\w)\\\*(?=(?:,|$))", "", text)


def _apply_project_patch_to_bullet_refs(
    refs: list[_ExperienceBulletRef],
    project_patch: ProjectPatch | None,
) -> list[_ExperienceBulletRef] | None:
    if project_patch is None:
        return refs

    refs_by_target = {(ref.role_id, ref.bullet_id): ref for ref in refs}
    rendered_text = {target: ref.rendered_text for target, ref in refs_by_target.items()}
    for operation in project_patch.operations:
        op_name = str(operation.get("op", "")).strip()
        if op_name == "replace-project-summary":
            continue
        if op_name != "replace-experience-bullet":
            return None
        role_id = slugify(operation.get("role_id", ""))
        bullet_id = slugify(operation.get("bullet_id", ""))
        old_text = operation.get("old_text")
        new_text = operation.get("new_text")
        if (
            not role_id
            or not bullet_id
            or not isinstance(old_text, str)
            or not isinstance(new_text, str)
        ):
            return None
        target = (role_id, bullet_id)
        ref = refs_by_target.get(target)
        if ref is None or ref.source_text != old_text:
            return None
        rendered_text[target] = _normalize_markdown_text(new_text)

    return [
        _ExperienceBulletRef(
            role_id=ref.role_id,
            bullet_id=ref.bullet_id,
            heading=ref.heading,
            source_text=ref.source_text,
            rendered_text=rendered_text[(ref.role_id, ref.bullet_id)],
        )
        for ref in refs
    ]


def _apply_project_patch_to_project_refs(
    refs: list[_ProjectSummaryRef],
    project_patch: ProjectPatch | None,
) -> list[_ProjectSummaryRef] | None:
    if project_patch is None:
        return refs

    refs_by_target = {ref.project_id: ref for ref in refs}
    rendered_text = {project_id: ref.rendered_text for project_id, ref in refs_by_target.items()}
    for operation in project_patch.operations:
        op_name = str(operation.get("op", "")).strip()
        if op_name == "replace-experience-bullet":
            continue
        if op_name != "replace-project-summary":
            return None
        project_id = slugify(operation.get("project_id", ""))
        old_text = operation.get("old_text")
        new_text = operation.get("new_text")
        if not project_id or not isinstance(old_text, str) or not isinstance(new_text, str):
            return None
        ref = refs_by_target.get(project_id)
        if ref is None or ref.source_text != old_text:
            return None
        rendered_text[project_id] = _normalize_markdown_text(new_text)

    return [
        _ProjectSummaryRef(
            project_id=ref.project_id,
            heading=ref.heading,
            source_text=ref.source_text,
            rendered_text=rendered_text[ref.project_id],
        )
        for ref in refs
    ]
