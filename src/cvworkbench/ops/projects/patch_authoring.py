"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/patch_authoring.py

Author guarded proposals through captured document reads and cooperative write locks.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import copy
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any

import yaml

from cvworkbench.ops.projects.patches import (
    compile_project_patch,
    read_experience_bullet_text,
    read_project_patch_document,
    read_project_summary_text,
)
from cvworkbench.ops.projects.records import (
    _PROJECT_OP_REPLACE_EXPERIENCE_BULLET,
    _PROJECT_OP_REPLACE_PROJECT_SUMMARY,
    _PROJECT_PATCH_FORMAT_OPS,
    ProjectError,
    ProjectPatch,
    ProjectPatchDocument,
    _now_iso,
)
from cvworkbench.storage import AtomicWriteError, replace_files_atomically
from cvworkbench.text import slugify

_PROJECT_PATCH_MUTEXES: dict[str, Lock] = {}
_PROJECT_PATCH_MUTEXES_GUARD = Lock()


def append_replace_experience_bullet_operation(
    *,
    project_dir: Path,
    sot_path: Path,
    role_id: str,
    bullet_id: str,
    new_text: str,
    old_text: str | None = None,
) -> ProjectPatch:
    resolved_role_id = _require_project_text(role_id, field_name="role_id", slug=True)
    resolved_bullet_id = _require_project_text(bullet_id, field_name="bullet_id", slug=True)
    resolved_new_text = _require_project_text(new_text, field_name="new_text")
    current_text = read_experience_bullet_text(
        sot_path=sot_path,
        role_id=resolved_role_id,
        bullet_id=resolved_bullet_id,
    )
    resolved_old_text = (
        current_text if old_text is None else _require_project_text(old_text, field_name="old_text")
    )
    if resolved_old_text == resolved_new_text:
        raise ProjectError("Project op replacement text must differ from source text")

    return _append_project_operation(
        project_dir=project_dir,
        sot_path=sot_path,
        operation=_experience_bullet_operation(
            role_id=resolved_role_id,
            bullet_id=resolved_bullet_id,
            old_text=resolved_old_text,
            new_text=resolved_new_text,
        ),
    )


def append_replace_project_summary_operation(
    *,
    project_dir: Path,
    sot_path: Path,
    project_id: str,
    new_text: str,
    old_text: str | None = None,
) -> ProjectPatch:
    resolved_project_id = _require_project_text(project_id, field_name="project_id", slug=True)
    resolved_new_text = _require_project_text(new_text, field_name="new_text")
    current_text = read_project_summary_text(
        sot_path=sot_path,
        project_id=resolved_project_id,
    )
    resolved_old_text = (
        current_text if old_text is None else _require_project_text(old_text, field_name="old_text")
    )
    if resolved_old_text == resolved_new_text:
        raise ProjectError("Project op replacement text must differ from source text")

    return _append_project_operation(
        project_dir=project_dir,
        sot_path=sot_path,
        operation=_project_summary_operation(
            project_id=resolved_project_id,
            old_text=resolved_old_text,
            new_text=resolved_new_text,
        ),
    )


def _experience_bullet_operation(
    *,
    role_id: str,
    bullet_id: str,
    old_text: str,
    new_text: str,
) -> dict[str, str]:
    return {
        "op": _PROJECT_OP_REPLACE_EXPERIENCE_BULLET,
        "role_id": role_id,
        "bullet_id": bullet_id,
        "old_text": old_text,
        "new_text": new_text,
    }


def _project_summary_operation(
    *,
    project_id: str,
    old_text: str,
    new_text: str,
) -> dict[str, str]:
    return {
        "op": _PROJECT_OP_REPLACE_PROJECT_SUMMARY,
        "project_id": project_id,
        "old_text": old_text,
        "new_text": new_text,
    }


def _append_project_operation(
    *,
    project_dir: Path,
    sot_path: Path,
    operation: dict[str, str],
) -> ProjectPatch:
    try:
        patch_path = _authoring_patch_path(project_dir)
        project_root = patch_path.parent.parent
        initial = read_project_patch_document(patch_path)
        _candidate_patch(initial, operation, sot_path)
        with _project_patch_authoring_lock(patch_path):
            _authoring_patch_path(project_root)
            document = read_project_patch_document(patch_path)
            candidate = _candidate_patch(document, operation, sot_path)

            raw = copy.deepcopy(document.data)
            raw["patch"]["operations"] = list(candidate.operations)
            raw.setdefault("created_at", _now_iso())
            raw["updated_at"] = _now_iso()
            replace_files_atomically(
                [(patch_path, yaml.safe_dump(raw, sort_keys=False).encode("utf-8"))],
                expected_contents={patch_path: document.contents},
            )
    except (OSError, AtomicWriteError) as exc:
        raise ProjectError(f"Project patch update failed: {exc}") from exc
    return candidate


def _authoring_patch_path(project_dir: Path) -> Path:
    try:
        root = project_dir.resolve()
        path = root / "proposals/patch.yaml"
        inside_project = path.resolve().is_relative_to(root)
        regular = not path.is_symlink() and (not path.exists() or path.is_file())
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProjectError("Project patch destination could not be resolved") from exc
    if not regular:
        raise ProjectError("Project patch destination must be a regular file")
    if not inside_project:
        raise ProjectError("Project patch destination must stay inside the project")
    return path


@contextmanager
def _project_patch_authoring_lock(patch_path: Path):
    path_key = str(patch_path.resolve())
    with _PROJECT_PATCH_MUTEXES_GUARD:
        mutex = _PROJECT_PATCH_MUTEXES.setdefault(path_key, Lock())

    with mutex:
        lock_path = patch_path.with_name(f"{patch_path.name}.lock")
        flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        if lock_path.is_symlink() or (lock_path.exists() and not lock_path.is_file()):
            raise ProjectError("Project patch lock must be a regular file")
        try:
            descriptor = os.open(lock_path, flags | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            descriptor = os.open(lock_path, flags)
        with os.fdopen(descriptor, "r+b") as handle:
            opened = os.fstat(handle.fileno())
            current = lock_path.lstat()
            if opened.st_nlink != 1:
                raise ProjectError("Project patch lock must have a single filesystem link")
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
                current.st_dev,
                current.st_ino,
            ):
                raise ProjectError("Project patch lock ownership changed")
            if opened.st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            _lock_project_patch_handle(handle)
            try:
                yield
            finally:
                _unlock_project_patch_handle(handle)


def _lock_project_patch_handle(handle: Any) -> None:
    try:
        import fcntl
    except ImportError:
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock_project_patch_handle(handle: Any) -> None:
    try:
        import fcntl
    except ImportError:
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _require_project_text(value: str, *, field_name: str, slug: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectError(f"Project op field '{field_name}' must be a non-empty string")
    normalized = value.strip()
    if not slug:
        return normalized
    resolved = slugify(normalized)
    if not resolved:
        raise ProjectError(f"Project op field '{field_name}' must resolve to a stable id")
    return resolved


def _candidate_patch(
    document: ProjectPatchDocument, operation: dict[str, str], sot_path: Path
) -> ProjectPatch:
    candidate = ProjectPatch(_PROJECT_PATCH_FORMAT_OPS, "", (*document.patch.operations, operation))
    compile_project_patch(patch=candidate, sot_path=sot_path)
    return candidate
