"""Capture regular source files and directories for independent version copies."""

from __future__ import annotations

import stat
from dataclasses import dataclass, field
from pathlib import Path

from cvworkbench.ops.sot_versions.records import SotPackError


@dataclass(frozen=True)
class CapturedSource:
    files: dict[Path, tuple[bytes, int]] = field(repr=False)
    directories: dict[Path, int] = field(repr=False)


def capture_source(source: Path) -> CapturedSource:
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
    return CapturedSource(files, directories)
