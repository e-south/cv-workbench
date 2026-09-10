"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/review/packs.py

Packages selected run artifacts for document review.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from cvworkbench.config import resolve_project_path, resolve_reviews_path
from cvworkbench.ops.review import ReviewError
from cvworkbench.ops.review.targets import require_run_output, resolve_review_target


@dataclass(frozen=True)
class ReviewPack:
    out_dir: Path
    docx_path: Path
    pdf_path: Path
    review_path: Path
    run_id: str


def build_review_pack(
    *,
    variant_id: str | None,
    config_path: Path,
    run: str | None = None,
    project_dir: Path | None = None,
    out_dir: Path | None = None,
    force: bool = False,
) -> ReviewPack:
    resolution = resolve_review_target(
        config_path=config_path,
        run=run,
        variant_id=variant_id,
        project_dir=project_dir,
    )

    docx_source = require_run_output(resolution.run, "docx")
    pdf_source = require_run_output(resolution.run, "pdf")
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
