"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/runs.py

Own exclusive run allocation and remove only still-owned empty directories on failure.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


@contextmanager
def allocate_run(runs_root: Path) -> Iterator[Path]:
    """Retain a fresh run on success; leave foreign or unrecovered artifacts intact."""
    created: dict[Path, tuple[int, int]] = {}
    try:
        missing = []
        current = runs_root
        while not current.exists():
            missing.append(current)
            current = current.parent
        for directory in reversed(missing):
            try:
                directory.mkdir()
            except FileExistsError:
                if not directory.is_dir():
                    raise
            else:
                _record_directory(directory, created)
        base_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        for suffix in range(1000):
            name = base_timestamp if suffix == 0 else f"{base_timestamp}-{suffix:02d}"
            run_dir = runs_root / name
            try:
                run_dir.mkdir()
            except FileExistsError:
                continue
            _record_directory(run_dir, created)
            break
        else:
            raise RuntimeError(
                f"Could not allocate unique run directory for timestamp: {base_timestamp}"
            )
        yield run_dir
    except BaseException as exc:
        retained: list[Path] = []
        for directory, identity in reversed(created.items()):
            try:
                current = directory.lstat()
                if (current.st_dev, current.st_ino) != identity:
                    raise OSError("Directory ownership changed")
                directory.rmdir()
            except FileNotFoundError:
                continue
            except OSError:
                if not any(path.is_relative_to(directory) for path in retained):
                    exc.add_note(f"Build directory retained for inspection: {directory}")
                    retained.append(directory)
        raise


def _record_directory(path: Path, created: dict[Path, tuple[int, int]]) -> None:
    metadata = path.lstat()
    created[path] = (metadata.st_dev, metadata.st_ino)
