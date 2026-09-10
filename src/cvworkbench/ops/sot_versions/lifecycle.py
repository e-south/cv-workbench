"""List, copy, and activate versions within an existing source pack."""

from __future__ import annotations

import shutil
from pathlib import Path

from cvworkbench.inputs.sot_versions import SotVersionError, resolve_versioned_root
from cvworkbench.ops.sot_versions.records import (
    SotPackError,
    SotVersionState,
    _validate_version_name,
)


def list_versions(root: Path) -> SotVersionState:
    root = resolve_versioned_root(root)
    versions_dir = root / "versions"
    versions = sorted([path.name for path in versions_dir.iterdir() if path.is_dir()])
    if not versions:
        raise SotPackError(f"No SoT versions found under: {versions_dir}")
    active = _read_active(root)
    return SotVersionState(root=root, versions=versions, active=active)


def create_version(root: Path, name: str, base: str) -> Path:
    root = resolve_versioned_root(root)
    _validate_version_name(name)
    _validate_version_name(base)
    base_dir = root / "versions" / base
    if not base_dir.exists():
        raise SotPackError(f"Base SoT version not found: {base_dir}")
    target_dir = root / "versions" / name
    if target_dir.exists():
        raise SotPackError(f"SoT version already exists: {target_dir}")
    shutil.copytree(base_dir, target_dir)
    return target_dir


def activate_version(root: Path, name: str) -> None:
    root = resolve_versioned_root(root)
    _validate_version_name(name)
    target_dir = root / "versions" / name
    if not target_dir.exists():
        raise SotPackError(f"SoT version not found: {target_dir}")
    (root / "ACTIVE").write_text(f"{name}\n")


def _read_active(root: Path) -> str:
    active_path = root / "ACTIVE"
    if not active_path.exists():
        raise SotVersionError(f"Active SoT file not found: {active_path}")
    value = active_path.read_text().strip()
    if not value:
        raise SotVersionError("Active SoT version is empty")
    return value
