"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/review/importing.py

Converts reviewed DOCX edits into guarded patch proposals.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cvworkbench.config import resolve_drafts_path
from cvworkbench.ops.review import ReviewError
from cvworkbench.ops.review.patches import build_import_patch
from cvworkbench.ops.review.record import (
    SOURCE_RECORD_NAME,
    load_source_record,
    validate_source_artifacts,
)
from cvworkbench.ops.review.targets import resolve_review_target


@dataclass(frozen=True)
class ImportResult:
    draft_dir: Path
    patch_path: Path
    metadata_path: Path
    notes_path: Path
    imported_path: Path
    run_id: str
    apply_status: str


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
    if project_dir is not None and variant_id is not None:
        raise ReviewError("--project cannot be combined with --variant")

    source_path = docx_path.parent / SOURCE_RECORD_NAME
    source = load_source_record(source_path) if source_path.exists() else None
    if source is None and not run:
        raise ReviewError("DOCX without a review source record requires an explicit --run")
    if source is not None:
        validate_source_artifacts(source)
    resolution = resolve_review_target(
        config_path=config_path,
        run=run or (source.run_path if source is not None else None),
        variant_id=None if source is not None else variant_id,
        project_dir=project_dir,
    )
    if source is not None:
        if (
            resolution.run.path.resolve() != Path(source.run_path).resolve()
            or resolution.run_id != source.run_id
        ):
            raise ReviewError("Selected run conflicts with review source")
        if variant_id is not None and resolution.run.variant_id != variant_id:
            raise ReviewError("Selected variant conflicts with review source")
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

    patch_name, patch_text, apply_status, note_lines = build_import_patch(
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
    raise ReviewError(
        f"Could not allocate unique import draft directory for timestamp: {base_name}"
    )
