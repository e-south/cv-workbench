"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/apply.py

Applies draft patches to Source of Truth data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import subprocess
from pathlib import Path


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

    patch_exe = _which("patch")
    if patch_exe is None:
        raise ApplyError("patch is required but was not found in PATH")

    if patch_path.read_text().strip() == "":
        return

    _run_patch(patch_exe, sot_path, patch_path, dry_run=True)
    _run_patch(patch_exe, sot_path, patch_path, dry_run=False)


def _run_patch(patch_exe: str, cwd: Path, patch_path: Path, *, dry_run: bool) -> None:
    args = [patch_exe, "-p0", "-i", str(patch_path)]
    if dry_run:
        args.insert(1, "--dry-run")
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise ApplyError(message or "Patch failed")


def _which(command: str) -> str | None:
    result = subprocess.run(["/usr/bin/which", command], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()
