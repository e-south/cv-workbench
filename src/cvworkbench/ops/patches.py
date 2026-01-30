"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/patches.py

Applies unified diff patches to a target directory.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class PatchError(RuntimeError):
    pass


def apply_patch_file(*, patch_path: Path, cwd: Path) -> None:
    if not patch_path.exists():
        raise PatchError(f"Patch file not found: {patch_path}")
    patch_text = patch_path.read_text()
    apply_patch_text(patch_text=patch_text, cwd=cwd, patch_path=patch_path)


def apply_patch_text(*, patch_text: str, cwd: Path, patch_path: Path | None = None) -> None:
    patch_text = patch_text or ""
    if patch_text.strip() == "":
        return
    patch_exe = _which("patch")
    if patch_exe is None:
        raise PatchError("patch is required but was not found in PATH")

    target_path = patch_path
    if target_path is None:
        target_path = cwd / ".cvw.patch.tmp"
        target_path.write_text(patch_text)

    try:
        _run_patch(patch_exe, cwd, target_path, dry_run=True)
        _run_patch(patch_exe, cwd, target_path, dry_run=False)
    finally:
        if target_path.name == ".cvw.patch.tmp":
            target_path.unlink(missing_ok=True)


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
        raise PatchError(message or "Patch failed")


def _which(command: str) -> str | None:
    result = subprocess.run(
        ["/usr/bin/which", command], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()
