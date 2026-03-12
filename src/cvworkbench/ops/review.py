"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/review.py

Builds review packs and imports DOCX review edits as patch proposals.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from difflib import unified_diff
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from cvworkbench.build.selection import build_selection
from cvworkbench.config import (
    resolve_drafts_path,
    resolve_project_path,
    resolve_reviews_path,
    resolve_runs_path,
    resolve_sot_path,
    resolve_variant_path,
)
from cvworkbench.inputs.sot import load_sot
from cvworkbench.inputs.sot_versions import resolve_active_sot_path
from cvworkbench.ops.projects import (
    ProjectError,
    ProjectPatch,
    compile_project_patch,
    load_project,
    load_project_patch_payload,
    resolve_project_dir,
)
from cvworkbench.ops.runs import (
    RunError,
    RunInfo,
    resolve_latest_project_run,
    resolve_latest_run,
    resolve_run,
)
from cvworkbench.text import slugify
from cvworkbench.variants import Variant, load_variant


class ReviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReviewPack:
    out_dir: Path
    docx_path: Path
    pdf_path: Path
    review_path: Path
    run_id: str


@dataclass(frozen=True)
class ImportResult:
    draft_dir: Path
    patch_path: Path
    metadata_path: Path
    notes_path: Path
    imported_path: Path
    run_id: str
    apply_status: str


def build_review_pack(
    *,
    variant_id: str | None,
    config_path: Path,
    run: str | None = None,
    project_dir: Path | None = None,
    out_dir: Path | None = None,
    force: bool = False,
) -> ReviewPack:
    resolution = _resolve_review_target(
        config_path=config_path,
        run=run,
        variant_id=variant_id,
        project_dir=project_dir,
    )

    docx_source = _require_run_output(resolution.run, "docx")
    pdf_source = _require_run_output(resolution.run, "pdf")
    selection_path = resolution.run.path / "selection.json"
    if not docx_source.exists():
        raise ReviewError(f"Missing DOCX output: {docx_source}")
    if not pdf_source.exists():
        raise ReviewError(f"Missing PDF output: {pdf_source}")
    if not selection_path.exists():
        raise ReviewError(f"Missing selection metadata: {selection_path}")

    reviews_root = resolve_reviews_path(config_path)
    if out_dir is None:
        target_dir = reviews_root / resolution.review_dir
    else:
        target_dir = resolve_project_path(out_dir, config_path)
    if target_dir.exists():
        if not force:
            raise ReviewError(f"Review pack already exists: {target_dir}")
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=False)

    docx_target = target_dir / docx_source.name
    pdf_target = target_dir / pdf_source.name
    shutil.copy2(docx_source, docx_target)
    shutil.copy2(pdf_source, pdf_target)

    review_path = target_dir / "review.md"
    review_path.write_text(_build_review_checklist(selection_path))

    return ReviewPack(
        out_dir=target_dir,
        docx_path=docx_target,
        pdf_path=pdf_target,
        review_path=review_path,
        run_id=resolution.run_id,
    )


def import_docx_review(
    *,
    docx_path: Path,
    config_path: Path,
    run: str | None,
    variant_id: str | None,
    project_dir: Path | None,
) -> ImportResult:
    if not docx_path.exists():
        raise ReviewError(f"DOCX file not found: {docx_path}")

    resolution = _resolve_review_target(
        config_path=config_path,
        run=run,
        variant_id=variant_id,
        project_dir=project_dir,
    )
    run_id = resolution.run_id
    run_dir = resolution.run.path
    canonical_path = run_dir / "canonical.md"
    if not canonical_path.exists():
        raise ReviewError(f"Canonical markdown not found: {canonical_path}")

    imported_markdown = _convert_docx_to_markdown(docx_path)
    drafts_root = resolve_drafts_path(config_path)
    draft_dir = _create_import_draft_dir(drafts_root)

    imported_path = draft_dir / "imported.md"
    imported_path.write_text(imported_markdown)

    patch_name, patch_text, apply_status, note_lines = _build_import_patch(
        canonical_path=canonical_path,
        imported_markdown=imported_markdown,
        sot_path=resolution.sot_path,
        variant=resolution.variant,
        project_patch=resolution.project_patch,
    )
    patch_path = draft_dir / patch_name
    patch_path.write_text(patch_text)

    metadata_path = draft_dir / "draft.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source": "import-docx",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id,
                "variant_id": resolution.variant.id,
                "review_dir": str(resolution.review_dir),
                "canonical_path": str(canonical_path),
                "canonical_hash": _hash_file(canonical_path),
                "imported_path": str(imported_path),
                "patch_path": patch_name,
                "apply_status": apply_status,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    notes_path = draft_dir / "notes.md"
    notes_path.write_text(
        "\n".join(
            [
                "# Import Notes",
                "",
                f"- source: {docx_path}",
                f"- canonical: {canonical_path}",
                f"- apply_status: {apply_status}",
                "",
                *note_lines,
            ]
        )
        + "\n"
    )

    return ImportResult(
        draft_dir=draft_dir,
        patch_path=patch_path,
        metadata_path=metadata_path,
        notes_path=notes_path,
        imported_path=imported_path,
        run_id=run_id,
        apply_status=apply_status,
    )


def _build_review_checklist(selection_path: Path) -> str:
    selection = json.loads(selection_path.read_text())
    items = selection.get("items", [])
    lines = ["# Review Checklist", ""]
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "bullet":
            continue
        if item.get("included") is not True:
            continue
        bullet_id = item.get("id", "")
        text = item.get("text") or ""
        role_id = item.get("role_id") or ""
        label = f"{bullet_id} ({role_id})".strip()
        if text:
            lines.append(f"- [ ] {label}: {text}")
        else:
            lines.append(f"- [ ] {label}")
    lines.append("")
    return "\n".join(lines)


def _convert_docx_to_markdown(docx_path: Path) -> str:
    pandoc_path = _which("pandoc")
    if pandoc_path is None:
        raise ReviewError("pandoc is required to import DOCX")

    result = subprocess.run(
        [pandoc_path, "--to", "markdown", str(docx_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise ReviewError(message or "Pandoc conversion failed")
    return result.stdout.strip() + "\n"


def _resolve_run_dir(
    config_path: Path,
    run: str | None,
    variant_id: str | None,
    project_dir: Path | None,
) -> tuple[str, Path]:
    if project_dir is not None and variant_id is not None:
        raise ReviewError("--project cannot be combined with --variant")

    if project_dir is not None:
        try:
            project = load_project(project_dir)
        except ProjectError as exc:
            raise ReviewError(str(exc)) from exc
        try:
            if run:
                resolved_run = _resolve_project_run(config_path, project.project_id, run)
            else:
                resolved_run = resolve_latest_project_run(config_path, project.project_id)
        except RunError as exc:
            raise ReviewError(str(exc)) from exc
        return resolved_run.run_id, resolved_run.path

    if run:
        try:
            resolved_run = resolve_run(config_path, run)
        except RunError as exc:
            raise ReviewError(str(exc)) from exc
        return resolved_run.run_id, resolved_run.path

    try:
        latest = resolve_latest_run(
            config_path,
            variant_id=variant_id,
            include_project_runs=False,
        )
    except RunError as exc:
        raise ReviewError(str(exc)) from exc
    return latest.run_id, latest.path


@dataclass(frozen=True)
class _ReviewTarget:
    run_id: str
    run: RunInfo
    variant: Variant
    review_dir: Path
    sot_path: Path
    project_patch: ProjectPatch | None


def _resolve_review_target(
    *,
    config_path: Path,
    run: str | None,
    variant_id: str | None,
    project_dir: Path | None,
) -> _ReviewTarget:
    if project_dir is not None and variant_id is not None:
        raise ReviewError("--project cannot be combined with --variant")

    project = None
    project_patch: ProjectPatch | None = None
    if project_dir is not None:
        try:
            project = load_project(project_dir)
            project_patch = load_project_patch_payload(project.patch_path)
        except ProjectError as exc:
            raise ReviewError(str(exc)) from exc
        try:
            run_info = (
                _resolve_project_run(config_path, project.project_id, run)
                if run
                else resolve_latest_project_run(config_path, project.project_id)
            )
        except RunError as exc:
            raise ReviewError(str(exc)) from exc
    elif run:
        try:
            run_info = resolve_run(config_path, run)
        except RunError as exc:
            raise ReviewError(str(exc)) from exc
        project = _load_project_for_run(config_path, run_info.run_id)
        if project is not None:
            try:
                project_patch = load_project_patch_payload(project.patch_path)
            except ProjectError as exc:
                raise ReviewError(str(exc)) from exc
    else:
        try:
            run_info = resolve_latest_run(
                config_path,
                variant_id=variant_id,
                include_project_runs=False,
            )
        except RunError as exc:
            raise ReviewError(str(exc)) from exc

    if project is not None:
        variant = load_variant(project.variant_path)
        review_dir = Path("projects") / project.project_id
        sot_path = resolve_active_sot_path(project.sot_path)
    else:
        variant_path = resolve_variant_path(run_info.variant_id, config_path)
        if not variant_path.exists():
            raise ReviewError(f"Variant not found: {run_info.variant_id}")
        variant = load_variant(variant_path)
        review_dir = Path(variant.id)
        sot_path = resolve_sot_path(None, config_path)

    return _ReviewTarget(
        run_id=run_info.run_id,
        run=run_info,
        variant=variant,
        review_dir=review_dir,
        sot_path=sot_path,
        project_patch=project_patch,
    )


def _require_run_output(run: RunInfo, fmt: str) -> Path:
    output_name = run.outputs.get(fmt)
    if not output_name:
        raise ReviewError(f"Selected run does not include {fmt} output: {run.run_id}")
    run_root = run.path.resolve()
    path = (run.path / output_name).resolve()
    try:
        path.relative_to(run_root)
    except ValueError as exc:
        raise ReviewError(
            f"Selected run {fmt} output escapes run directory: {output_name}"
        ) from exc
    if not path.exists():
        raise ReviewError(
            f"Selected run is missing immutable {fmt} output: {path}. "
            "Rebuild the target run with the current cv-workbench version."
        )
    return path


def _resolve_project_run(config_path: Path, project_id: str, run: str) -> RunInfo:
    runs_root = resolve_runs_path(config_path)
    project_runs_root = runs_root / "projects" / project_id
    candidate = Path(run)
    try:
        if candidate.exists():
            resolved = resolve_run(config_path, candidate)
        elif (project_runs_root / run).exists():
            resolved = resolve_run(config_path, project_runs_root / run)
        else:
            resolved = resolve_run(config_path, run)
    except RunError as exc:
        raise ReviewError(str(exc)) from exc
    if not resolved.run_id.startswith(f"projects/{project_id}/"):
        raise ReviewError(f"Run does not belong to project: {project_id}")
    return resolved


def _load_project_for_run(config_path: Path, run_id: str) -> Any | None:
    parts = Path(run_id).parts
    if len(parts) < 3 or parts[0] != "projects":
        return None
    project_id = parts[1]
    project_dir = resolve_project_dir(project_id, config_path)
    try:
        return load_project(project_dir)
    except ProjectError:
        return None


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


def _build_import_patch(
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

    for canonical_token, imported_token in zip(canonical_tokens, imported_tokens):
        if (
            canonical_token.kind != imported_token.kind
            or canonical_token.section != imported_token.section
            or canonical_token.heading != imported_token.heading
        ):
            return None
        if canonical_token.text == imported_token.text:
            continue
        if _normalize_noneditable_token_text(canonical_token.text) == _normalize_noneditable_token_text(
            imported_token.text
        ):
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
        token for token in canonical_tokens if token.kind == "bullet" and token.section == "Experience"
    ]
    imported_experience = [
        token for token in imported_tokens if token.kind == "bullet" and token.section == "Experience"
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
        for canonical_token, ref in zip(canonical_experience, bullet_refs):
            if canonical_token.heading != ref.heading or canonical_token.text != ref.rendered_text:
                return None
    if canonical_projects:
        if len(canonical_projects) != len(project_refs):
            return None
        for canonical_token, ref in zip(canonical_projects, project_refs):
            if canonical_token.heading != ref.heading or canonical_token.text != ref.rendered_text:
                return None

    operations: list[dict[str, str]] = []
    for canonical_token, imported_token, ref in zip(
        canonical_experience,
        imported_experience,
        bullet_refs,
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
    for canonical_token, imported_token, ref in zip(canonical_projects, imported_projects, project_refs):
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
        if isinstance(item, dict)
        and item.get("type") == "bullet"
        and item.get("included") is True
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
            tokens.append(_MarkdownToken(kind="section", section=section, heading=None, text=section))
            continue
        if line.startswith("### "):
            flush_paragraph()
            heading = _normalize_markdown_text(line[4:])
            tokens.append(_MarkdownToken(kind="heading", section=section, heading=heading, text=heading))
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
        if not role_id or not bullet_id or not isinstance(old_text, str) or not isinstance(new_text, str):
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


def _which(command: str) -> str | None:
    result = subprocess.run(
        ["/usr/bin/which", command], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _create_import_draft_dir(drafts_root: Path) -> Path:
    drafts_root.mkdir(parents=True, exist_ok=True)
    base_name = f"import-{_timestamp()}"
    for suffix in range(0, 1000):
        name = base_name if suffix == 0 else f"{base_name}-{suffix:02d}"
        candidate = drafts_root / name
        try:
            candidate.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            continue
        return candidate
    raise ReviewError(f"Could not allocate unique import draft directory for timestamp: {base_name}")
