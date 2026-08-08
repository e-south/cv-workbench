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
from dataclasses import dataclass
from pathlib import Path


class AtomicWriteError(RuntimeError):
    pass


@dataclass(frozen=True)
class _StagedWrite:
    destination: Path
    staged: Path
    backup: Path | None


def replace_files_atomically(writes: list[tuple[Path, bytes]]) -> None:
    """Stage every payload, then replace all destinations with rollback on failure."""

    destinations = [destination for destination, _ in writes]
    if len(destinations) != len(set(destinations)):
        raise AtomicWriteError("Atomic replacement destinations must be unique")

    staged_writes: list[_StagedWrite] = []
    applied: list[_StagedWrite] = []
    try:
        for destination, content in writes:
            destination.parent.mkdir(parents=True, exist_ok=True)
            staged = _temporary_sibling(destination, "stage")
            staged.write_bytes(content)
            mode = stat.S_IMODE(destination.stat().st_mode) if destination.exists() else 0o644
            staged.chmod(mode)
            backup: Path | None = None
            if destination.exists():
                backup = _temporary_sibling(destination, "backup")
                shutil.copy2(destination, backup)
            staged_writes.append(
                _StagedWrite(destination=destination, staged=staged, backup=backup)
            )

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
        if rollback_errors:
            raise AtomicWriteError("Atomic replacement failed and rollback was incomplete") from exc
        raise AtomicWriteError("Atomic replacement failed; prior artifacts were restored") from exc
    finally:
        for staged_write in staged_writes:
            staged_write.staged.unlink(missing_ok=True)
            if staged_write.backup is not None:
                staged_write.backup.unlink(missing_ok=True)


def _temporary_sibling(destination: Path, role: str) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{destination.name}.cvw-{role}-",
        dir=destination.parent,
    )
    os.close(descriptor)
    return Path(raw_path)
