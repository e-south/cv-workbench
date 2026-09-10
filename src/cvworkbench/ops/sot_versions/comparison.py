"""Compare version-owned YAML and declared snippets without writes."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Iterable

import yaml

from cvworkbench.inputs.sot import OPTIONAL_FILES, REQUIRED_FILES
from cvworkbench.inputs.sot_versions import (
    SotVersionError,
    resolve_version_directory,
    resolve_versioned_root,
)
from cvworkbench.ops.sot_versions.records import SotPackError, _validate_version_name


def diff_versions(root: Path, left: str, right: str) -> str:
    root = resolve_versioned_root(root)
    _validate_version_name(left)
    _validate_version_name(right)
    left_dir = _comparison_version(root, left)
    right_dir = _comparison_version(root, right)

    files = _collect_sot_files(left_dir, right_dir)
    diffs: list[str] = []
    for rel_path in files:
        left_path = _version_file(left_dir, rel_path)
        right_path = _version_file(right_dir, rel_path)
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


def _comparison_version(root: Path, name: str) -> Path:
    try:
        return resolve_version_directory(root, name)
    except SotVersionError as exc:
        raise SotPackError(str(exc)) from exc


def _version_file(version_dir: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise SotPackError(f"SoT file path must be relative to its version: {relative}")
    path = version_dir / relative
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as exc:
        raise SotPackError(f"Cannot resolve SoT file: {path}") from exc
    if not resolved.is_relative_to(version_dir):
        raise SotPackError(f"SoT file must remain within its version: {relative}")
    return path


def _collect_sot_files(left_dir: Path, right_dir: Path) -> list[Path]:
    files: set[Path] = set()
    for filename in list(REQUIRED_FILES.keys()) + list(OPTIONAL_FILES.keys()):
        left_path = _version_file(left_dir, Path(filename))
        right_path = _version_file(right_dir, Path(filename))
        if left_path.exists() or right_path.exists():
            files.add(Path(filename))

    for base in (left_dir, right_dir):
        snippets_file = _version_file(base, Path("snippets.yaml"))
        if snippets_file.exists():
            for snippet in _snippet_paths(snippets_file):
                files.add(Path(snippet))
    return sorted(files, key=lambda path: path.as_posix())


def _snippet_paths(snippets_file: Path) -> Iterable[str]:
    raw = _read_yaml_mapping(snippets_file)
    snippets = raw.get("snippets")
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
    return _read_text(path).strip()


def _normalize_yaml(path: Path) -> str:
    return yaml.safe_dump(_read_yaml_mapping(path), sort_keys=True).strip()


def _read_yaml_mapping(path: Path) -> dict:
    text = _read_text(path)
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SotPackError(f"Invalid YAML in {path.name}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise SotPackError(f"{path.name} must be a YAML mapping")
    return raw


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SotPackError(f"Cannot read SoT file as UTF-8: {path}") from exc
