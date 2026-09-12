"""Source-version operation results and domain error translation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cvworkbench.inputs.sot_versions import SotVersionError, validate_version_name


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
    try:
        validate_version_name(name)
    except SotVersionError as exc:
        raise SotPackError(str(exc)) from exc
