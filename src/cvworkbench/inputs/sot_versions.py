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
    versions_dir = path / "versions"
    active_path = path / "ACTIVE"
    if not any(marker.exists() or marker.is_symlink() for marker in (versions_dir, active_path)):
        return path
    if not versions_dir.is_dir():
        raise SotVersionError(f"SoT versions directory not found: {versions_dir}")

    active = _read_active(path)
    active_dir = (versions_dir / active).resolve()
    if not active_dir.is_relative_to(versions_dir):
        raise SotVersionError("Active SoT version must stay within the pack's versions directory")
    if not active_dir.exists():
        raise SotVersionError(f"Active SoT version not found: {active_dir}")
    if not active_dir.is_dir():
        raise SotVersionError(f"Active SoT version must be a directory: {active_dir}")
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
    if not active_path.is_file():
        raise SotVersionError(f"Active SoT selection must be a regular file: {active_path}")
    try:
        value = active_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise SotVersionError(
            f"Active SoT selection must be readable UTF-8: {active_path}"
        ) from exc
    if not value:
        raise SotVersionError("Active SoT version is empty")
    if Path(value).name != value or value in {".", ".."}:
        raise SotVersionError("Active SoT version contains invalid characters")
    return value
