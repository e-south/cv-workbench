"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/apply.py

Applies draft patches to Source of Truth data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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

    patch_payload_path = draft_dir / "patch.yaml"
    patch_path = draft_dir / "patch.diff"
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
