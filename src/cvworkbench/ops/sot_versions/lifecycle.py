"""List, copy, and activate versions within an existing source pack."""

from __future__ import annotations

from pathlib import Path

from cvworkbench.inputs.sot_versions import (
    read_active_version,
    resolve_version_directory,
    resolve_versioned_root,
)
from cvworkbench.ops.sot_versions.copying import capture_source
from cvworkbench.ops.sot_versions.records import (
    SotPackError,
    SotVersionState,
    _validate_version_name,
)
from cvworkbench.storage import AtomicWriteError, replace_files_atomically


def list_versions(root: Path) -> SotVersionState:
    root = resolve_versioned_root(root)
    versions_dir = root / "versions"
    versions = sorted([path.name for path in versions_dir.iterdir() if path.is_dir()])
    if not versions:
        raise SotPackError(f"No SoT versions found under: {versions_dir}")
    active = read_active_version(root)
    return SotVersionState(root=root, versions=versions, active=active)


def create_version(root: Path, name: str, base: str) -> Path:
    root = resolve_versioned_root(root)
    _validate_version_name(name)
    _validate_version_name(base)
    base_dir = resolve_version_directory(root, base)
    target_dir = root / "versions" / name
    if target_dir.exists() or target_dir.is_symlink():
        raise SotPackError(f"SoT version already exists: {target_dir}")
    captured = capture_source(base_dir)
    if capture_source(base_dir) != captured:
        raise SotPackError("Source changed during version cloning; no version was created")
    writes = [(target_dir / path, payload) for path, (payload, _) in captured.files.items()]
    try:
        replace_files_atomically(
            writes,
            file_modes={target_dir / path: mode for path, (_, mode) in captured.files.items()},
            new_directories={
                target_dir / path: mode for path, mode in captured.directories.items()
            },
            expected_contents={path: None for path, _ in writes},
        )
    except AtomicWriteError as exc:
        raise SotPackError(f"SoT version cloning failed: {exc}") from exc
    return target_dir


def activate_version(root: Path, name: str) -> None:
    root = resolve_versioned_root(root)
    _validate_version_name(name)
    resolve_version_directory(root, name)
    active_path = root / "ACTIVE"
    if active_path.is_symlink() or not active_path.is_file():
        raise SotPackError(f"Active SoT selection must be a regular file: {active_path}")
    try:
        previous = active_path.read_bytes()
        replace_files_atomically(
            [(active_path, f"{name}\n".encode("utf-8"))],
            expected_contents={active_path: previous},
        )
    except (OSError, AtomicWriteError) as exc:
        raise SotPackError(f"SoT activation failed: {exc}") from exc
