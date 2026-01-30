"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/apply.py

Applies draft patches to Source of Truth data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from cvworkbench.ops.patches import PatchError, apply_patch_file

class ApplyError(RuntimeError):
    pass


def apply_draft(*, draft_dir: Path, sot_path: Path) -> None:
    if not draft_dir.exists():
        raise ApplyError(f"Draft directory not found: {draft_dir}")
    if not sot_path.exists():
        raise ApplyError(f"SoT path not found: {sot_path}")

    patch_path = draft_dir / "patch.diff"
    if not patch_path.exists():
        raise ApplyError(f"Patch file not found: {patch_path}")

    if patch_path.read_text().strip() == "":
        return

    try:
        apply_patch_file(patch_path=patch_path, cwd=sot_path)
    except PatchError as exc:
        raise ApplyError(str(exc)) from exc
