"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/review.py

Builds review packs and imports DOCX review edits as patch proposals.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
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
from cvworkbench.ops.projects import ProjectError, load_project, resolve_project_dir
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

    patch_text, apply_status, note_lines = _build_import_patch(
        canonical_path=canonical_path,
        imported_markdown=imported_markdown,
        sot_path=resolution.sot_path,
        variant=resolution.variant,
    )
    patch_path = draft_dir / "patch.diff"
    patch_path.write_text(patch_text)

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
    if project_dir is not None:
        try:
            project = load_project(project_dir)
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
    )


def _require_run_output(run: RunInfo, fmt: str) -> Path:
    output_name = run.outputs.get(fmt)
    if not output_name:
        raise ReviewError(f"Selected run does not include {fmt} output: {run.run_id}")
    path = run.path / output_name
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
    text: str


def _build_import_patch(
    *,
    canonical_path: Path,
    imported_markdown: str,
    sot_path: Path,
    variant: Variant,
) -> tuple[str, str, list[str]]:
    supported = _build_experience_bullet_patch(
        canonical_markdown=canonical_path.read_text(),
        imported_markdown=imported_markdown,
        sot_path=sot_path,
        variant=variant,
    )
    if supported is not None:
        return (
            supported,
            "ready",
            [
                "This draft matched supported experience bullet text edits.",
                "patch.diff targets SoT files and can be applied after review.",
            ],
        )
    return (
        _diff_text(canonical_path, imported_markdown),
        "review_diff_only",
        [
            "This draft compares reviewed DOCX content against canonical.md.",
            "It is not directly applyable to SoT.",
            "Review the diff and author a real SoT patch manually.",
        ],
    )


def _build_experience_bullet_patch(
    *,
    canonical_markdown: str,
    imported_markdown: str,
    sot_path: Path,
    variant: Variant,
) -> str | None:
    if variant.document_type != "resume":
        return None

    canonical_tokens = _tokenize_markdown(canonical_markdown)
    imported_tokens = _tokenize_markdown(imported_markdown)
    if len(canonical_tokens) != len(imported_tokens):
        return None

    changed_bullets: list[tuple[str | None, str, str]] = []
    for canonical_token, imported_token in zip(canonical_tokens, imported_tokens):
        if (
            canonical_token.kind != imported_token.kind
            or canonical_token.section != imported_token.section
            or canonical_token.heading != imported_token.heading
        ):
            return None
        if canonical_token.text == imported_token.text:
            continue
        if canonical_token.kind != "bullet" or canonical_token.section != "Experience":
            return None
        changed_bullets.append(
            (canonical_token.heading, canonical_token.text, imported_token.text)
        )

    sot = load_sot(sot_path)
    bullet_refs = _selected_experience_bullets(sot, variant)
    canonical_experience = [
        token for token in canonical_tokens if token.kind == "bullet" and token.section == "Experience"
    ]
    if len(canonical_experience) != len(bullet_refs):
        return None
    for token, ref in zip(canonical_experience, bullet_refs):
        if token.heading != ref.heading or token.text != ref.text:
            return None

    updates: dict[tuple[str, str], str] = {}
    for heading, old_text, new_text in changed_bullets:
        ref = next(
            (
                item
                for item in bullet_refs
                if item.heading == heading and item.text == old_text
            ),
            None,
        )
        if ref is None:
            return None
        updates[(ref.role_id, ref.bullet_id)] = new_text

    original_path = sot_path / "experience.yaml"
    original_text = original_path.read_text()
    raw = yaml.safe_load(original_text)
    if not isinstance(raw, dict):
        return None
    roles = raw.get("roles")
    if not isinstance(roles, list):
        return None

    for role in roles:
        if not isinstance(role, dict):
            continue
        role_id = slugify(role.get("id", ""))
        bullets = role.get("bullets")
        if not isinstance(bullets, list):
            continue
        for bullet in bullets:
            if not isinstance(bullet, dict):
                continue
            bullet_id = slugify(bullet.get("id", ""))
            replacement = updates.get((role_id, bullet_id))
            if replacement is not None:
                bullet["text"] = replacement

    updated_text = yaml.safe_dump(raw, sort_keys=False)
    diff = unified_diff(
        original_text.splitlines(),
        updated_text.splitlines(),
        fromfile="experience.yaml",
        tofile="experience.yaml",
        lineterm="",
    )
    return "\n".join(diff) + ("\n" if original_text or updated_text else "")


def _selected_experience_bullets(
    sot: dict[str, Any],
    variant: Variant,
) -> list[_ExperienceBulletRef]:
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
                    heading=heading,
                    text=text.strip(),
                )
            )
    return refs


def _tokenize_markdown(markdown: str) -> list[_MarkdownToken]:
    tokens: list[_MarkdownToken] = []
    section: str | None = None
    heading: str | None = None
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line or line == ":::" or line.startswith("::: "):
            continue
        if line.startswith("## "):
            section = line[3:].strip()
            heading = None
            tokens.append(_MarkdownToken(kind="section", section=section, heading=None, text=section))
            continue
        if line.startswith("### "):
            heading = line[4:].strip()
            tokens.append(_MarkdownToken(kind="heading", section=section, heading=heading, text=heading))
            continue
        if line.startswith("- "):
            tokens.append(
                _MarkdownToken(
                    kind="bullet",
                    section=section,
                    heading=heading,
                    text=line[2:].strip(),
                )
            )
            continue
        tokens.append(_MarkdownToken(kind="text", section=section, heading=heading, text=line))
    return tokens


def _which(command: str) -> str | None:
    result = subprocess.run(
        ["/usr/bin/which", command], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


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
