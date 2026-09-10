"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/atomic.py

Applies small groups of file replacements as one recoverable transaction.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class AtomicWriteError(RuntimeError):
    pass


@dataclass(frozen=True)
class _StagedWrite:
    destination: Path
    staged: Path
    backup: Path | None


def replace_files_atomically(
    writes: list[tuple[Path, bytes]],
    *,
    file_modes: Mapping[Path, int] | None = None,
    expected_contents: Mapping[Path, bytes | None] | None = None,
) -> None:
    """Stage all payloads and recover prior files after replacement failures.

    Expected contents are checked before and after staging; None requires an
    absent destination. These byte checks do not lock out concurrent writers.
    """

    destinations = [destination for destination, _ in writes]
    if len(destinations) != len(set(destinations)):
        raise AtomicWriteError("Atomic replacement destinations must be unique")
    modes = file_modes or {}
    if not set(modes).issubset(destinations) or any(
        type(mode) is not int or not 0 <= mode <= 0o777 for mode in modes.values()
    ):
        raise AtomicWriteError("File modes must name write destinations and valid permission bits")
    if expected_contents is not None and not isinstance(expected_contents, Mapping):
        raise AtomicWriteError(
            "Expected contents must be a mapping of destinations to bytes or None"
        )
    expected = dict(expected_contents) if expected_contents is not None else {}
    if not set(expected).issubset(destinations) or any(
        content is not None and not isinstance(content, bytes) for content in expected.values()
    ):
        raise AtomicWriteError("Expected contents must name write destinations and bytes or None")

    staged_writes: list[_StagedWrite] = []
    applied: list[_StagedWrite] = []
    temporary_paths: set[Path] = set()
    recovery_backups: set[Path] = set()
    try:
        _check_expected_contents(expected)
        for destination, content in writes:
            destination.parent.mkdir(parents=True, exist_ok=True)
            staged = _temporary_sibling(destination, "stage")
            temporary_paths.add(staged)
            staged.write_bytes(content)
            mode = modes.get(destination)
            if mode is None:
                mode = stat.S_IMODE(destination.stat().st_mode) if destination.exists() else 0o644
            staged.chmod(mode)
            backup: Path | None = None
            if destination.exists():
                backup = _temporary_sibling(destination, "backup")
                temporary_paths.add(backup)
                shutil.copy2(destination, backup)
            staged_writes.append(
                _StagedWrite(destination=destination, staged=staged, backup=backup)
            )

        _check_expected_contents(expected)
        for staged_write in staged_writes:
            os.replace(staged_write.staged, staged_write.destination)
            applied.append(staged_write)
    except OSError as exc:
        rollback_errors: list[OSError] = []
        for staged_write in reversed(applied):
            try:
                if staged_write.backup is None:
                    staged_write.destination.unlink(missing_ok=True)
                else:
                    os.replace(staged_write.backup, staged_write.destination)
            except OSError as rollback_exc:
                rollback_errors.append(rollback_exc)
                if staged_write.backup is not None:
                    recovery_backups.add(staged_write.backup)
        if rollback_errors:
            retained = ", ".join(str(path) for path in sorted(recovery_backups))
            detail = f"; recovery backups retained at: {retained}" if retained else ""
            raise AtomicWriteError(
                f"Atomic replacement failed and rollback was incomplete{detail}"
            ) from exc
        raise AtomicWriteError("Atomic replacement failed; prior artifacts were restored") from exc
    finally:
        for path in temporary_paths - recovery_backups:
            path.unlink(missing_ok=True)


def _check_expected_contents(expected: Mapping[Path, bytes | None]) -> None:
    for path, content in expected.items():
        try:
            current = path.read_bytes()
        except FileNotFoundError:
            current = None
        if current != content or (current is None and path.is_symlink()):
            raise AtomicWriteError(f"Artifact changed since it was read; no files replaced: {path}")


def _temporary_sibling(destination: Path, role: str) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{destination.name}.cvw-{role}-",
        dir=destination.parent,
    )
    os.close(descriptor)
    return Path(raw_path)
