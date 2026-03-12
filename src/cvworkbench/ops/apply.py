"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/apply.py

Applies draft patches to Source of Truth data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cvworkbench.ops.patches import PatchError, apply_patch_file
from cvworkbench.ops.projects import ProjectError, compile_project_patch, load_project_patch_payload


class ApplyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApplyResult:
    patch_path: Path
    status: str
    reason: str


def apply_draft(*, draft_dir: Path, sot_path: Path) -> ApplyResult:
    if not draft_dir.exists():
        raise ApplyError(f"Draft directory not found: {draft_dir}")
    if not sot_path.exists():
        raise ApplyError(f"SoT path not found: {sot_path}")

    metadata = _load_draft_metadata(draft_dir / "draft.json")
    if metadata is None and ((draft_dir / "imported.md").exists() or (draft_dir / "notes.md").exists()):
        raise ApplyError(f"Import draft metadata not found: {draft_dir / 'draft.json'}")
    apply_status = _metadata_text(metadata, "apply_status")
    if apply_status == "review_diff_only":
        raise ApplyError(
            "Draft metadata marks apply_status: review_diff_only; inspect notes.md and "
            "author an explicit SoT patch instead of applying this draft"
        )

    patch_payload_path = draft_dir / "patch.yaml"
    patch_path = draft_dir / "patch.diff"
    metadata_patch_name = _metadata_text(metadata, "patch_path")
    if metadata_patch_name:
        expected_patch = draft_dir / metadata_patch_name
        if patch_payload_path.exists() and expected_patch != patch_payload_path:
            raise ApplyError("Draft metadata patch_path does not match patch.yaml")
        if patch_path.exists() and expected_patch != patch_path:
            raise ApplyError("Draft metadata patch_path does not match patch.diff")
    if patch_payload_path.exists():
        try:
            patch = load_project_patch_payload(patch_payload_path)
            patch_text = compile_project_patch(patch=patch, sot_path=sot_path)
        except ProjectError as exc:
            raise ApplyError(str(exc)) from exc
        if patch_text.strip() == "":
            reason = (
                "compiled_noop"
                if patch.format == "project-ops" and len(patch.operations) > 0
                else "empty_patch"
            )
            return ApplyResult(
                patch_path=patch_payload_path,
                status="no_changes",
                reason=reason,
            )
        try:
            from cvworkbench.ops.patches import apply_patch_text

            apply_patch_text(patch_text=patch_text, cwd=sot_path)
        except PatchError as exc:
            raise ApplyError(str(exc)) from exc
        return ApplyResult(
            patch_path=patch_payload_path,
            status="applied",
            reason="mutation_applied",
        )

    if not patch_path.exists():
        raise ApplyError(f"Patch file not found: {patch_payload_path} or {patch_path}")

    if patch_path.read_text().strip() == "":
        return ApplyResult(
            patch_path=patch_path,
            status="no_changes",
            reason="empty_patch",
        )

    try:
        apply_patch_file(patch_path=patch_path, cwd=sot_path)
    except PatchError as exc:
        raise ApplyError(str(exc)) from exc
    return ApplyResult(
        patch_path=patch_path,
        status="applied",
        reason="mutation_applied",
    )


def _load_draft_metadata(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ApplyError(f"Draft metadata is invalid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ApplyError(f"Draft metadata must be an object: {path}")
    return raw


def _metadata_text(metadata: dict[str, Any] | None, key: str) -> str | None:
    if metadata is None:
        return None
    value = metadata.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApplyError(f"Draft metadata field '{key}' must be a string")
    return value.strip() or None
