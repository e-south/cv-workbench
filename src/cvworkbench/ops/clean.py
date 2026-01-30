"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/clean.py

Cleans generated artifacts to control workspace bloat.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


class CleanError(RuntimeError):
    pass


@dataclass(frozen=True)
class CleanResult:
    target: str
    path: Path
    removed: int
    status: str


def clean_path(*, target: str, path: Path, confirm: bool) -> CleanResult:
    if not path.exists():
        raise CleanError(f"Target path not found: {path}")
    if not path.is_dir():
        raise CleanError(f"Target path is not a directory: {path}")

    entries = list(path.iterdir())
    if not entries:
        return CleanResult(target=target, path=path, removed=0, status="empty")

    if not confirm:
        return CleanResult(target=target, path=path, removed=len(entries), status="dry_run")

    removed = 0
    for entry in entries:
        if entry.is_symlink() or entry.is_file():
            entry.unlink()
            removed += 1
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
            removed += 1
            continue
        raise CleanError(f"Unsupported entry type: {entry}")

    return CleanResult(target=target, path=path, removed=removed, status="cleaned")
