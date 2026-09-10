"""Source-version results, errors, and name constraints."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class SotPackError(RuntimeError):
    pass


@dataclass(frozen=True)
class SotVersionState:
    root: Path
    versions: list[str]
    active: str


@dataclass(frozen=True)
class InitializedSotPack:
    source: Path
    root: Path
    active: str

    @property
    def version(self) -> Path:
        return self.root / "versions" / self.active


def _validate_version_name(name: str) -> None:
    if not name.strip():
        raise SotPackError("SoT version name is required")
    if (
        Path(name).name != name
        or name in {".", ".."}
        or name != name.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise SotPackError("SoT version name contains invalid characters")
