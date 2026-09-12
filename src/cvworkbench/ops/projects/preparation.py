"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/preparation.py

Prepare project edits in an exclusively owned copy without replacing source inputs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import shutil
from pathlib import Path

from cvworkbench.ops.patches import PatchError, apply_patch_text
from cvworkbench.ops.projects.patches import load_project_patch
from cvworkbench.ops.projects.records import ProjectError


def prepare_project_sot(*, project_dir: Path, sot_path: Path, target_dir: Path) -> Path:
    """Apply project edits to a fresh copy, or return the source for an empty patch."""
    try:
        source = sot_path.resolve()
        source_exists = source.is_dir()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProjectError("Project source path could not be resolved") from exc
    if not source_exists:
        raise ProjectError(f"Project source directory not found: {source}")
    diff = load_project_patch(project_dir, sot_path=source)
    if not diff.strip():
        return source
    target = _preparation_destination(project_dir, source, target_dir)
    try:
        target.mkdir(parents=True, exist_ok=False)
        identity = _directory_identity(target)
    except OSError as exc:
        raise ProjectError(
            f"Project preparation destination could not be created: {target}"
        ) from exc
    try:
        shutil.copytree(source, target, dirs_exist_ok=True)
        apply_patch_text(patch_text=diff, cwd=target)
    except BaseException as exc:
        try:
            _cleanup_preparation(target, identity)
        except (OSError, ProjectError) as cleanup_exc:
            detail = f"Project preparation cleanup failed: {cleanup_exc}"
            if isinstance(exc, Exception):
                raise ProjectError(f"{exc}; {detail}") from exc
            exc.add_note(detail)
        if isinstance(exc, (OSError, PatchError)):
            raise ProjectError(f"Project source preparation failed: {exc}") from exc
        raise
    return target


def _preparation_destination(project_dir: Path, source: Path, target_dir: Path) -> Path:
    try:
        target = target_dir.resolve()
        project = project_dir.resolve()
        target_exists = target_dir.is_symlink() or target.exists()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProjectError("Project preparation destination could not be resolved") from exc
    for owner in (source, project):
        if target.is_relative_to(owner) or owner.is_relative_to(target):
            raise ProjectError("Project preparation destination must not overlap source or project")
    if target_exists:
        raise ProjectError(f"Project preparation destination already exists: {target_dir}")
    return target


def _directory_identity(path: Path) -> tuple[int, int]:
    metadata = path.lstat()
    return metadata.st_dev, metadata.st_ino


def _cleanup_preparation(path: Path, expected_identity: tuple[int, int]) -> None:
    try:
        observed = _directory_identity(path)
    except FileNotFoundError:
        return
    if observed != expected_identity:
        raise ProjectError(f"Preparation directory was replaced; left intact: {path}")
    shutil.rmtree(path)
