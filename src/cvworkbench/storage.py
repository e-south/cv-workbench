"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/storage.py

Applies small groups of file replacements as one recoverable transaction.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


class AtomicWriteError(RuntimeError):
    pass


@dataclass(frozen=True)
class _StagedWrite:
    destination: Path
    staged: Path | None
    backup: Path | None


def replace_files_atomically(
    writes: list[tuple[Path, bytes]],
    *,
    delete_paths: Sequence[Path] = (),
    file_modes: Mapping[Path, int] | None = None,
    new_directories: Mapping[Path, int] | None = None,
    expected_contents: Mapping[Path, bytes | None] | None = None,
) -> None:
    """Stage all payloads and recover prior files after replacement failures.

    Expected contents are checked before and after staging; None requires an
    absent destination. These byte checks do not lock out concurrent writers.
    """

    write_destinations = [destination for destination, _ in writes]
    destinations = [*write_destinations, *delete_paths]
    if len(destinations) != len({path.resolve() for path in destinations}):
        raise AtomicWriteError("Atomic replacement destinations must be unique")
    modes = file_modes or {}
    if new_directories is not None and not isinstance(new_directories, Mapping):
        raise AtomicWriteError("New directories must be a mapping of paths to permission bits")
    directory_modes = dict(new_directories) if new_directories is not None else {}
    if len(directory_modes) != len({path.resolve() for path in directory_modes}) or any(
        type(mode) is not int or not 0 <= mode <= 0o777 for mode in directory_modes.values()
    ):
        raise AtomicWriteError("New directories must be unique and have valid permission bits")
    if set(path.resolve() for path in directory_modes) & {path.resolve() for path in destinations}:
        raise AtomicWriteError("New directories must not overlap file destinations")
    if not set(modes).issubset(write_destinations) or any(
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
    created_directories: dict[Path, tuple[int, int]] = {}
    committed = False
    try:
        _check_expected_contents(expected)
        for directory in directory_modes:
            if directory.exists() or directory.is_symlink():
                raise AtomicWriteError(f"New directory must be absent: {directory}")
        for destination in destinations:
            if destination.is_symlink() or (destination.exists() and not destination.is_file()):
                raise AtomicWriteError(
                    f"Artifact destinations must be regular files or absent: {destination}"
                )
        for directory in sorted(directory_modes, key=lambda path: len(path.parts)):
            _ensure_parent(directory.parent, created_directories)
            directory.mkdir(mode=0o700)
            metadata = directory.lstat()
            created_directories[directory] = (metadata.st_dev, metadata.st_ino)
        for destination, content in writes:
            _ensure_parent(destination.parent, created_directories)
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
        for destination in delete_paths:
            if destination.exists():
                backup = _temporary_sibling(destination, "backup")
                temporary_paths.add(backup)
                shutil.copy2(destination, backup)
                staged_writes.append(_StagedWrite(destination, None, backup))

        _check_expected_contents(expected)
        for staged_write in staged_writes:
            # Register before replacement: cancellation may arrive after the syscall.
            applied.append(staged_write)
            if staged_write.staged is None:
                staged_write.destination.unlink()
            else:
                os.replace(staged_write.staged, staged_write.destination)
                temporary_paths.discard(staged_write.staged)
        for directory in sorted(directory_modes, key=lambda path: len(path.parts), reverse=True):
            directory.chmod(directory_modes[directory])
        committed = True
    except BaseException as exc:
        rollback_errors: list[OSError] = []
        # Restore access before removing files from a newly created restrictive tree.
        for directory in sorted(directory_modes, key=lambda path: len(path.parts)):
            if directory not in created_directories:
                continue
            try:
                metadata = directory.lstat()
                if (metadata.st_dev, metadata.st_ino) != created_directories[directory]:
                    raise OSError(f"New directory ownership changed: {directory}")
                directory.chmod(0o700)
            except OSError as rollback_exc:
                rollback_errors.append(rollback_exc)
        for staged_write in reversed(applied):
            try:
                # A refused replacement leaves its staged source in place.
                # A completed syscall consumes it, even if cancellation follows.
                if staged_write.staged is None and (
                    staged_write.destination.exists() or staged_write.destination.is_symlink()
                ):
                    continue
                if staged_write.staged is not None and staged_write.staged.exists():
                    continue
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
            message = f"Atomic replacement failed and rollback was incomplete{detail}"
            if isinstance(exc, OSError):
                raise AtomicWriteError(message) from exc
            exc.add_note(message)
        elif isinstance(exc, OSError):
            raise AtomicWriteError(
                "Atomic replacement failed; prior artifacts were restored"
            ) from exc
        raise
    finally:
        for path in temporary_paths - recovery_backups:
            path.unlink(missing_ok=True)
        if not committed:
            for directory, identity in reversed(created_directories.items()):
                try:
                    current = directory.lstat()
                    if (current.st_dev, current.st_ino) == identity:
                        directory.rmdir()
                except OSError:
                    # Preserve nonempty/replaced directories and any recovery copies.
                    continue


def _ensure_parent(path: Path, created: dict[Path, tuple[int, int]]) -> None:
    missing = []
    current = path
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
            identity = directory.lstat()
            created[directory] = (identity.st_dev, identity.st_ino)


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
