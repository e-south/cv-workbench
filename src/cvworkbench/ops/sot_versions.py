"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/sot_versions.py

Operations for versioned Source of Truth (SoT) packs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
import difflib
from pathlib import Path
import shutil
from typing import Iterable

import yaml

from cvworkbench.inputs.sot import OPTIONAL_FILES, REQUIRED_FILES
from cvworkbench.inputs.sot_versions import SotVersionError, resolve_versioned_root


class SotPackError(RuntimeError):
    pass


@dataclass(frozen=True)
class SotVersionState:
    root: Path
    versions: list[str]
    active: str


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


def diff_versions(root: Path, left: str, right: str) -> str:
    root = resolve_versioned_root(root)
    _validate_version_name(left)
    _validate_version_name(right)
    left_dir = root / "versions" / left
    right_dir = root / "versions" / right
    if not left_dir.exists():
        raise SotPackError(f"SoT version not found: {left_dir}")
    if not right_dir.exists():
        raise SotPackError(f"SoT version not found: {right_dir}")

    files = _collect_sot_files(left_dir, right_dir)
    diffs: list[str] = []
    for rel_path in files:
        left_path = left_dir / rel_path
        right_path = right_dir / rel_path
        left_text = _read_file(left_path)
        right_text = _read_file(right_path)
        if left_text == right_text:
            continue
        diff = difflib.unified_diff(
            left_text.splitlines(),
            right_text.splitlines(),
            fromfile=str(rel_path),
            tofile=str(rel_path),
            lineterm="",
        )
        diffs.extend(diff)
    return "\n".join(diffs)


def _collect_sot_files(left_dir: Path, right_dir: Path) -> list[Path]:
    files: set[Path] = set()
    for filename in list(REQUIRED_FILES.keys()) + list(OPTIONAL_FILES.keys()):
        left_path = left_dir / filename
        right_path = right_dir / filename
        if left_path.exists() or right_path.exists():
            files.add(Path(filename))

    for base in (left_dir, right_dir):
        snippets_file = base / "snippets.yaml"
        if snippets_file.exists():
            for snippet in _snippet_paths(snippets_file):
                files.add(Path(snippet))
    return sorted(files, key=lambda path: path.as_posix())


def _snippet_paths(snippets_file: Path) -> Iterable[str]:
    raw = yaml.safe_load(snippets_file.read_text())
    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise SotPackError(f"{snippets_file.name} must be a YAML mapping")
    snippets = raw.get("snippets", {}).get("snippets")
    if snippets is None:
        return []
    if not isinstance(snippets, list):
        raise SotPackError("snippets.snippets must be a list")
    paths: list[str] = []
    for snippet in snippets:
        if not isinstance(snippet, dict):
            raise SotPackError("snippets.snippets entries must be mappings")
        path_value = snippet.get("path")
        if path_value is None:
            continue
        if not isinstance(path_value, str) or not path_value.strip():
            raise SotPackError("snippet path must be a string")
        paths.append(path_value)
    return paths


def _read_file(path: Path) -> str:
    if not path.exists():
        return ""
    if path.suffix == ".yaml":
        return _normalize_yaml(path)
    return path.read_text().strip()


def _normalize_yaml(path: Path) -> str:
    raw = yaml.safe_load(path.read_text())
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise SotPackError(f"{path.name} must be a YAML mapping")
    return yaml.safe_dump(raw, sort_keys=True).strip()


def _read_active(root: Path) -> str:
    active_path = root / "ACTIVE"
    if not active_path.exists():
        raise SotVersionError(f"Active SoT file not found: {active_path}")
    value = active_path.read_text().strip()
    if not value:
        raise SotVersionError("Active SoT version is empty")
    return value


def _validate_version_name(name: str) -> None:
    if not name.strip():
        raise SotPackError("SoT version name is required")
    if Path(name).name != name or name in {".", ".."}:
        raise SotPackError("SoT version name contains invalid characters")
