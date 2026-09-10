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
    """Identify a version container independently of its selection record."""
    versions = path / "versions"
    return not versions.is_symlink() and versions.is_dir()


def resolve_active_sot_path(path: Path) -> Path:
    path = path.resolve()
    versions_dir = path / "versions"
    active_path = path / "ACTIVE"
    if not any(marker.exists() or marker.is_symlink() for marker in (versions_dir, active_path)):
        return path
    if not versions_dir.is_dir():
        raise SotVersionError(f"SoT versions directory not found: {versions_dir}")

    return resolve_version_directory(path, read_active_version(path))


def resolve_version_directory(root: Path, name: str) -> Path:
    """Resolve a named directory confined to a source pack's versions directory."""
    validate_version_name(name)
    try:
        versions_dir = root.resolve() / "versions"
        selected = (versions_dir / name).resolve()
        contained = selected.is_relative_to(versions_dir)
        is_directory = contained and selected.is_dir()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SotVersionError("Cannot resolve SoT version directory") from exc
    if not contained:
        raise SotVersionError("SoT version must stay within the pack's versions directory")
    if not is_directory:
        raise SotVersionError(f"SoT version must be an existing directory: {selected}")
    return selected


def resolve_versioned_root(path: Path) -> Path:
    path = path.resolve()
    if is_versioned_root(path):
        return path
    if path.parent.name == "versions" and is_versioned_root(path.parent.parent):
        return path.parent.parent
    raise SotVersionError(f"SoT versions not initialized at: {path}")


def read_active_version(root: Path) -> str:
    """Read one UTF-8 selection record without following a symbolic link."""
    active_path = root / "ACTIVE"
    if active_path.is_symlink():
        raise SotVersionError(f"Active SoT selection must not be a symbolic link: {active_path}")
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
    validate_version_name(value)
    return value


def validate_version_name(name: str) -> None:
    """Require one version-name component that fits an ACTIVE record."""
    if not name.strip():
        raise SotVersionError("SoT version name is required")
    if (
        Path(name).name != name
        or name in {".", ".."}
        or name != name.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise SotVersionError("SoT version name contains invalid characters")
