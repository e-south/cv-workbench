"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/review/packs.py

Packages selected run artifacts for document review.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from cvworkbench.config import resolve_project_path, resolve_reviews_path
from cvworkbench.ops.review import ReviewError
from cvworkbench.ops.review.record import SOURCE_RECORD_NAME, create_source_record
from cvworkbench.ops.review.targets import require_run_output, resolve_review_run
from cvworkbench.storage import AtomicWriteError, replace_files_atomically


@dataclass(frozen=True)
class ReviewPack:
    out_dir: Path
    docx_path: Path
    pdf_path: Path
    review_path: Path
    run_id: str
    source_record_path: Path


def build_review_pack(
    *,
    variant_id: str | None,
    config_path: Path,
    run: str | None = None,
    project_dir: Path | None = None,
    out_dir: Path | None = None,
    force: bool = False,
) -> ReviewPack:
    resolution = resolve_review_run(
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

    source = create_source_record(resolution.run, docx_source, pdf_source)
    checklist = _build_review_checklist(selection_path)
    output_bytes = {path: path.read_bytes() for path in (docx_source, pdf_source)}
    for path, payload in output_bytes.items():
        name = path.relative_to(resolution.run.path.resolve()).as_posix()
        if hashlib.sha256(payload).hexdigest() != source.files[name]:
            raise ReviewError(f"Run output changed during review preparation: {path}")

    reviews_root = resolve_reviews_path(config_path)
    if out_dir is None:
        target_dir = reviews_root / resolution.review_dir
    else:
        target_dir = resolve_project_path(out_dir, config_path)
    target = target_dir.resolve()
    source_root = resolution.run.path.resolve()
    if reviews_root.resolve().is_relative_to(target):
        raise ReviewError(f"Review target must not replace the reviews store: {target_dir}")
    if target.is_relative_to(source_root) or source_root.is_relative_to(target):
        raise ReviewError(f"Review target overlaps its source run: {target_dir}")
    if target_dir.exists():
        if not force:
            raise ReviewError(f"Review pack already exists: {target_dir}")
    if target_dir.is_symlink():
        raise ReviewError(f"Review pack target must not be a symlink: {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)

    docx_target = target_dir / docx_source.name
    pdf_target = target_dir / pdf_source.name
    review_path = target_dir / "review.md"
    source_record_path = target_dir / SOURCE_RECORD_NAME
    writes = [
        (docx_target, output_bytes[docx_source]),
        (pdf_target, output_bytes[pdf_source]),
        (review_path, checklist.encode()),
        (source_record_path, (source.model_dump_json(indent=2) + "\n").encode()),
    ]
    try:
        replace_files_atomically(writes, file_modes={source_record_path: 0o600})
    except AtomicWriteError as exc:
        raise ReviewError(str(exc)) from exc
    if force:
        destinations = {path for path, _ in writes}
        for path in target_dir.iterdir():
            if path in destinations:
                continue
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()

    return ReviewPack(
        out_dir=target_dir,
        docx_path=docx_target,
        pdf_path=pdf_target,
        review_path=review_path,
        run_id=resolution.run.run_id,
        source_record_path=source_record_path,
    )


def _build_review_checklist(selection_path: Path) -> str:
    try:
        selection = json.loads(selection_path.read_text())
    except (OSError, ValueError) as exc:
        raise ReviewError(f"Selection metadata cannot be read: {selection_path}") from exc
    if not isinstance(selection, dict):
        raise ReviewError(f"Selection metadata must be an object: {selection_path}")
    items = selection.get("items", [])
    if not isinstance(items, list):
        raise ReviewError(f"Selection metadata items must be a list: {selection_path}")
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
