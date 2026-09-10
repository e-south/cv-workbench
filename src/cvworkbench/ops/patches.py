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
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

from cvworkbench.storage import AtomicWriteError, replace_files_atomically


class PatchError(RuntimeError):
    pass


@dataclass(frozen=True)
class _PatchTarget:
    relative: Path
    destination: Path
    before: bytes | None = field(repr=False)
    mode: int | None
    deleted: bool


def apply_patch_file(*, patch_path: Path, cwd: Path) -> None:
    if not patch_path.exists():
        raise PatchError(f"Patch file not found: {patch_path}")
    try:
        patch_text = patch_path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise PatchError(f"Patch file could not be read: {patch_path}") from exc
    apply_patch_text(patch_text=patch_text, cwd=cwd)


def apply_patch_text(*, patch_text: str, cwd: Path) -> None:
    if not isinstance(patch_text, str):
        raise PatchError("Patch text must be a string")
    if patch_text.strip() == "":
        return
    try:
        targets = _capture_patch_targets(patch_text=patch_text, cwd=cwd)
        patch_exe = _which("patch")
        if patch_exe is None:
            raise PatchError("patch is required but was not found in PATH")
        with TemporaryDirectory(prefix="cvw-patch-") as temporary:
            root = Path(temporary)
            staged_source = root / "source"
            staged_source.mkdir()
            captured_patch = root / "input.diff"
            captured_patch.write_text(patch_text)
            for target in targets:
                staged = staged_source / target.relative
                staged.parent.mkdir(parents=True, exist_ok=True)
                if target.before is not None:
                    staged.write_bytes(target.before)
            _run_patch(patch_exe, staged_source, captured_patch, dry_run=True)
            _run_patch(patch_exe, staged_source, captured_patch, dry_run=False)
            writes = []
            deletions = []
            for target in targets:
                staged = staged_source / target.relative
                if target.deleted:
                    if staged.exists() and staged.read_bytes():
                        raise PatchError(f"Patch did not remove its target: {target.relative}")
                    deletions.append(target.destination)
                else:
                    writes.append((target.destination, staged.read_bytes()))
            replace_files_atomically(
                writes,
                delete_paths=deletions,
                file_modes={
                    target.destination: (
                        target.mode
                        if target.mode is not None
                        else stat.S_IMODE((staged_source / target.relative).stat().st_mode)
                    )
                    for target in targets
                    if not target.deleted
                },
                expected_contents={target.destination: target.before for target in targets},
            )
    except (OSError, AtomicWriteError) as exc:
        raise PatchError(f"Patch application failed: {exc}") from exc


_PATCH_HEADER_RE = re.compile(r"^(---|\+\+\+) (?P<path>[^\t]+)")
_PATCH_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@(?:.*)$")
_NO_NEWLINE_MARKER = "\\ No newline at end of file"


def _capture_patch_targets(*, patch_text: str, cwd: Path) -> tuple[_PatchTarget, ...]:
    headers = _parse_patch_targets(patch_text)
    if not headers:
        raise PatchError("Patch does not include unified diff file headers")

    cwd_resolved = cwd.resolve()
    targets = []
    seen: set[Path] = set()
    for old_path, new_path in headers:
        resolved_old = _resolve_patch_target(old_path, cwd_resolved)
        resolved_new = _resolve_patch_target(new_path, cwd_resolved)
        if resolved_old is None and resolved_new is None:
            raise PatchError("Patch must name a source target")
        if resolved_old is not None and not resolved_old.exists():
            raise PatchError(f"Patch target does not exist under SoT: {old_path}")
        if resolved_old is not None and resolved_new is not None and old_path != new_path:
            raise PatchError("Patch file renames are unsupported; use matching file headers")
        if resolved_old is None and resolved_new is not None and not resolved_new.parent.exists():
            raise PatchError(f"Patch target parent does not exist under SoT: {new_path}")
        destination = resolved_old if resolved_old is not None else resolved_new
        assert destination is not None
        if destination in seen:
            raise PatchError(f"Duplicate patch target: {destination}")
        seen.add(destination)
        relative = Path(old_path if resolved_old is not None else new_path)
        lexical = cwd_resolved / relative
        if lexical.is_symlink() or (destination.exists() and not destination.is_file()):
            raise PatchError(f"Patch target must be a regular file or absent: {relative}")
        if resolved_old is None and destination.exists():
            raise PatchError(f"New patch target already exists: {relative}")
        before = destination.read_bytes() if destination.exists() else None
        mode = stat.S_IMODE(destination.stat().st_mode) if before is not None else None
        targets.append(_PatchTarget(relative, destination, before, mode, resolved_new is None))
    return tuple(targets)


def _parse_patch_targets(patch_text: str) -> list[tuple[str, str]]:
    lines = patch_text.splitlines()
    targets: list[tuple[str, str]] = []
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        if not lines[index].startswith("--- "):
            raise PatchError("Patch contains content outside a unified diff")
        if index + 1 >= len(lines) or not lines[index + 1].startswith("+++ "):
            raise PatchError("Patch is missing a +++ file header")
        old_path = _parse_patch_header(lines[index])
        new_path = _parse_patch_header(lines[index + 1])
        targets.append((old_path, new_path))
        index += 2
        hunks = 0
        while index < len(lines) and lines[index].startswith("@@ "):
            match = _PATCH_HUNK_RE.fullmatch(lines[index])
            if match is None:
                raise PatchError("Patch has an invalid unified hunk header")
            old_remaining, new_remaining = (
                int(count) if count is not None else 1 for count in match.groups()
            )
            index += 1
            while old_remaining or new_remaining:
                if index >= len(lines):
                    raise PatchError("Patch has a truncated unified hunk")
                line = lines[index]
                if line == _NO_NEWLINE_MARKER:
                    index += 1
                    continue
                if not line or line[0] not in " +-":
                    raise PatchError("Patch has invalid unified hunk content")
                old_remaining -= line[0] in " -"
                new_remaining -= line[0] in " +"
                if old_remaining < 0 or new_remaining < 0:
                    raise PatchError("Patch unified hunk line counts disagree")
                index += 1
            if index < len(lines) and lines[index] == _NO_NEWLINE_MARKER:
                index += 1
            hunks += 1
        if hunks == 0:
            raise PatchError("Patch file headers require a unified hunk")
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
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PatchError(f"Patch target is outside SoT: {path_text}")
    resolved = (cwd / candidate).resolve()
    try:
        resolved.relative_to(cwd)
    except ValueError as exc:
        raise PatchError(f"Patch target is outside SoT: {path_text}") from exc
    return resolved


def _run_patch(patch_exe: str, cwd: Path, patch_path: Path, *, dry_run: bool) -> None:
    args = [patch_exe, "-u", "-f", "-F0", "-p0", "-i", str(patch_path)]
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
