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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cvworkbench.build.paths import output_path
from cvworkbench.config import (
    resolve_dist_path,
    resolve_drafts_path,
    resolve_project_path,
    resolve_reviews_path,
    resolve_runs_path,
    resolve_variant_path,
)
from cvworkbench.ops.projects import ProjectError, load_project, resolve_project_dir
from cvworkbench.ops.runs import (
    RunError,
    RunInfo,
    resolve_latest_project_run,
    resolve_latest_run,
    resolve_run,
)
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


def build_review_pack(
    *,
    variant_id: str | None,
    config_path: Path,
    run: str | None = None,
    project_dir: Path | None = None,
    out_dir: Path | None = None,
) -> ReviewPack:
    resolution = _resolve_review_target(
        config_path=config_path,
        run=run,
        variant_id=variant_id,
        project_dir=project_dir,
    )

    dist_dir = resolve_dist_path(config_path) / resolution.variant.id
    docx_source = output_path(dist_dir, resolution.variant, "docx")
    pdf_source = output_path(dist_dir, resolution.variant, "pdf")
    selection_path = dist_dir / "selection.json"
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
        raise ReviewError(f"Review pack already exists: {target_dir}")
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

    run_id, run_dir = _resolve_run_dir(config_path, run, variant_id, project_dir)
    canonical_path = run_dir / "canonical.md"
    if not canonical_path.exists():
        raise ReviewError(f"Canonical markdown not found: {canonical_path}")

    imported_markdown = _convert_docx_to_markdown(docx_path)
    drafts_root = resolve_drafts_path(config_path)
    draft_dir = drafts_root / f"import-{_timestamp()}"
    draft_dir.mkdir(parents=True, exist_ok=False)

    imported_path = draft_dir / "imported.md"
    imported_path.write_text(imported_markdown)

    patch_text = _diff_text(canonical_path, imported_markdown)
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
                "",
                "Review the diff before applying changes to SoT.",
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
        latest = resolve_latest_run(config_path, variant_id=variant_id)
    except RunError as exc:
        raise ReviewError(str(exc)) from exc
    return latest.run_id, latest.path


@dataclass(frozen=True)
class _ReviewTarget:
    run_id: str
    variant: Variant
    review_dir: Path


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
            run_info = resolve_latest_run(config_path, variant_id=variant_id)
        except RunError as exc:
            raise ReviewError(str(exc)) from exc

    if project is not None:
        variant = load_variant(project.variant_path)
        review_dir = Path("projects") / project.project_id
    else:
        variant_path = resolve_variant_path(run_info.variant_id, config_path)
        if not variant_path.exists():
            raise ReviewError(f"Variant not found: {run_info.variant_id}")
        variant = load_variant(variant_path)
        review_dir = Path(variant.id)

    return _ReviewTarget(
        run_id=run_info.run_id,
        variant=variant,
        review_dir=review_dir,
    )


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
    from difflib import unified_diff

    before = canonical_path.read_text().splitlines()
    after = imported_markdown.splitlines()
    diff = unified_diff(before, after, fromfile="canonical.md", tofile="imported.md", lineterm="")
    return "\n".join(diff) + ("\n" if before or after else "")


def _which(command: str) -> str | None:
    result = subprocess.run(
        ["/usr/bin/which", command], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
