"""Validate a captured source and create a fresh, independent version pack."""

from __future__ import annotations

import stat
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

from cvworkbench.inputs.sot import REQUIRED_FILES
from cvworkbench.inputs.sot_versions import resolve_active_sot_path
from cvworkbench.inputs.validation import validate_sot
from cvworkbench.ops.sot_versions.records import (
    InitializedSotPack,
    SotPackError,
    _validate_version_name,
)
from cvworkbench.storage import AtomicWriteError, replace_files_atomically


@dataclass(frozen=True)
class _CapturedSource:
    files: dict[Path, tuple[bytes, int]] = field(repr=False)
    directories: dict[Path, int] = field(repr=False)


def initialize_pack(*, source: Path, destination: Path, name: str = "base") -> InitializedSotPack:
    """Copy one selected source into a fresh pack without retargeting configuration."""
    _validate_version_name(name)
    try:
        source_owner = source.resolve()
        selected = resolve_active_sot_path(source_owner)
        target = destination.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SotPackError(f"Cannot resolve source-pack paths: {exc}") from exc
    if not selected.is_dir():
        raise SotPackError(f"Source directory not found: {selected}")
    for owner in (source_owner, selected):
        if target.is_relative_to(owner) or owner.is_relative_to(target):
            raise SotPackError("New pack destination must not overlap its source")
    if destination.is_symlink() or target.exists():
        raise SotPackError(f"New pack destination must be absent: {destination}")
    try:
        missing = [filename for filename in REQUIRED_FILES if not (selected / filename).is_file()]
    except OSError as exc:
        raise SotPackError(f"Cannot inspect required source files: {selected}") from exc
    if missing:
        raise SotPackError(f"Required source files missing: {', '.join(missing)}")

    captured = _capture_source(selected)
    _validate_captured_source(captured, selected)
    if _capture_source(selected) != captured:
        raise SotPackError("Source changed during pack initialization; no pack was created")

    result = InitializedSotPack(source=selected, root=target, active=name)
    writes = [(result.version / path, payload) for path, (payload, _) in captured.files.items()]
    modes = {result.version / path: mode for path, (_, mode) in captured.files.items()}
    # ACTIVE is written last, after every file in the initial version.
    writes.append((target / "ACTIVE", f"{name}\n".encode("utf-8")))
    modes[target / "ACTIVE"] = 0o600
    directories = {target: 0o700, target / "versions": 0o700}
    directories.update({result.version / path: mode for path, mode in captured.directories.items()})
    try:
        replace_files_atomically(
            writes,
            file_modes=modes,
            new_directories=directories,
            expected_contents={path: None for path, _ in writes},
        )
    except AtomicWriteError as exc:
        raise SotPackError(f"Source pack initialization failed: {exc}") from exc
    return result


def _capture_source(source: Path) -> _CapturedSource:
    files: dict[Path, tuple[bytes, int]] = {}
    directories: dict[Path, int] = {}
    try:
        for path in [source, *sorted(source.rglob("*"))]:
            relative = path.relative_to(source)
            mode = path.lstat().st_mode
            permissions = stat.S_IMODE(mode)
            if stat.S_ISDIR(mode):
                directories[relative] = permissions
            elif stat.S_ISREG(mode):
                files[relative] = (path.read_bytes(), permissions)
            else:
                raise SotPackError(
                    f"Source pack copying requires regular files/directories: {relative}"
                )
    except OSError as exc:
        raise SotPackError(f"Cannot capture source directory: {source}") from exc
    return _CapturedSource(files, directories)


def _validate_captured_source(captured: _CapturedSource, source: Path) -> None:
    with TemporaryDirectory(prefix="cvw-sot-pack-validation-") as temporary:
        staged = Path(temporary)
        try:
            for relative, (payload, _) in captured.files.items():
                path = staged / relative
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                path.write_bytes(payload)
                path.chmod(0o600)
            errors = validate_sot(staged)
        except (OSError, ValueError) as exc:
            raise SotPackError(f"Cannot validate captured source: {source}") from exc
        if errors:
            raise SotPackError(
                f"Source data is invalid; validate the selected source before creating a pack: {source}"
            )
