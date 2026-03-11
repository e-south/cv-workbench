"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/patches.py

Applies unified diff patches to a target directory.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import re
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
    _validate_patch_targets(patch_text=patch_text, cwd=cwd)
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


_PATCH_HEADER_RE = re.compile(r"^(---|\+\+\+) (?P<path>[^\t]+)")


def _validate_patch_targets(*, patch_text: str, cwd: Path) -> None:
    targets = _parse_patch_targets(patch_text)
    if not targets:
        raise PatchError("Patch does not include unified diff file headers")

    cwd_resolved = cwd.resolve()
    for old_path, new_path in targets:
        resolved_old = _resolve_patch_target(old_path, cwd_resolved)
        resolved_new = _resolve_patch_target(new_path, cwd_resolved)

        if resolved_old is not None and not resolved_old.exists():
            raise PatchError(f"Patch target does not exist under SoT: {old_path}")
        if resolved_old is None and resolved_new is not None and not resolved_new.parent.exists():
            raise PatchError(f"Patch target parent does not exist under SoT: {new_path}")
        if (
            resolved_old is not None
            and resolved_new is not None
            and not resolved_old.exists()
            and not resolved_new.exists()
        ):
            raise PatchError(f"Patch target does not exist under SoT: {old_path}")


def _parse_patch_targets(patch_text: str) -> list[tuple[str, str]]:
    lines = patch_text.splitlines()
    targets: list[tuple[str, str]] = []
    for index, line in enumerate(lines):
        if not line.startswith("--- "):
            continue
        if index + 1 >= len(lines) or not lines[index + 1].startswith("+++ "):
            raise PatchError("Patch is missing a +++ file header")
        old_path = _parse_patch_header(line)
        new_path = _parse_patch_header(lines[index + 1])
        targets.append((old_path, new_path))
    return targets


def _parse_patch_header(line: str) -> str:
    match = _PATCH_HEADER_RE.match(line)
    if not match:
        raise PatchError(f"Patch header is invalid: {line}")
    path = match.group("path").strip()
    if not path:
        raise PatchError("Patch header path is empty")
    return path


def _resolve_patch_target(path_text: str, cwd: Path) -> Path | None:
    if path_text == "/dev/null":
        return None
    candidate = Path(path_text)
    if candidate.is_absolute():
        raise PatchError(f"Patch target is outside SoT: {path_text}")
    resolved = (cwd / candidate).resolve()
    try:
        resolved.relative_to(cwd)
    except ValueError as exc:
        raise PatchError(f"Patch target is outside SoT: {path_text}") from exc
    return resolved


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
