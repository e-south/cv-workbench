"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/inputs/sot_versions.py

Resolves versioned Source of Truth (SoT) paths.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path


class SotVersionError(RuntimeError):
    pass


def is_versioned_root(path: Path) -> bool:
    return (path / "versions").is_dir() and (path / "ACTIVE").exists()


def resolve_active_sot_path(path: Path) -> Path:
    path = path.resolve()
    if not is_versioned_root(path):
        return path

    active = _read_active(path)
    active_dir = (path / "versions" / active).resolve()
    if not active_dir.exists():
        raise SotVersionError(f"Active SoT version not found: {active_dir}")
    return active_dir


def resolve_versioned_root(path: Path) -> Path:
    path = path.resolve()
    if is_versioned_root(path):
        return path
    if path.parent.name == "versions" and is_versioned_root(path.parent.parent):
        return path.parent.parent
    raise SotVersionError(f"SoT versions not initialized at: {path}")


def _read_active(root: Path) -> str:
    active_path = root / "ACTIVE"
    if not active_path.exists():
        raise SotVersionError(f"Active SoT file not found: {active_path}")
    value = active_path.read_text().strip()
    if not value:
        raise SotVersionError("Active SoT version is empty")
    if Path(value).name != value or value in {".", ".."}:
        raise SotVersionError("Active SoT version contains invalid characters")
    return value
