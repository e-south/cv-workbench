"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/review/record.py

Records and validates the immutable source of a content review bundle.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cvworkbench.ops.review import ReviewError

if TYPE_CHECKING:
    from cvworkbench.ops.runs import RunInfo

SOURCE_RECORD_NAME = "review-source.json"
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class SourceArtifactError(ReviewError):
    def __init__(self, state: Literal["missing", "changed", "invalid"], message: str):
        super().__init__(message)
        self.state = state


class ReviewSource(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[1]
    kind: Literal["content-review"]
    run_id: str
    run_path: str
    docx_name: str
    pdf_name: str
    files: dict[str, Digest]

    @field_validator("schema_version", mode="before")
    @classmethod
    def version_is_integer(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be an integer")
        return value

    @field_validator("run_id")
    @classmethod
    def relative_run_id(cls, value: str) -> str:
        _require_relative_path(value)
        return value

    @field_validator("run_path")
    @classmethod
    def absolute_run_path(cls, value: str) -> str:
        if not Path(value).is_absolute():
            raise ValueError("run_path must be absolute")
        return value

    @field_validator("docx_name", "pdf_name")
    @classmethod
    def bundle_filename(cls, value: str) -> str:
        _require_relative_path(value)
        if len(PurePosixPath(value).parts) != 1:
            raise ValueError("Review outputs must be filenames")
        return value

    @field_validator("files")
    @classmethod
    def source_files(cls, value: dict[str, str]) -> dict[str, str]:
        if not {"canonical.md", "manifest.json", "selection.json"}.issubset(value):
            raise ValueError("Review source is missing baseline artifacts")
        for name in value:
            _require_relative_path(name)
        return value

    @model_validator(mode="after")
    def review_outputs_are_recorded(self) -> Self:
        for name in (self.docx_name, self.pdf_name):
            if sum(PurePosixPath(path).name == name for path in self.files) != 1:
                raise ValueError(f"Review source must record exactly one output named {name}")
        if self.docx_name == self.pdf_name:
            raise ValueError("Review DOCX and PDF outputs must be distinct")
        return self


def _require_relative_path(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or path.as_posix() != value
        or value == "."
    ):
        raise ValueError("Review source paths must be normalized relative paths")


def hash_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def create_source_record(run: RunInfo, docx: Path, pdf: Path) -> ReviewSource:
    root = run.path.resolve()
    paths = [root / name for name in ("manifest.json", "canonical.md", "selection.json")]
    paths.extend((docx, pdf))
    hashes: dict[str, str] = {}
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ReviewError(f"Review baseline artifact is missing or outside its run: {path}")
        hashes[path.relative_to(root).as_posix()] = hash_file(path)
    return ReviewSource(
        schema_version=1,
        kind="content-review",
        run_id=run.run_id,
        run_path=str(root),
        docx_name=docx.name,
        pdf_name=pdf.name,
        files=hashes,
    )


def load_source_record(path: Path) -> ReviewSource:
    try:
        return ReviewSource.model_validate_json(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ReviewError(f"Invalid review source record: {path}: {exc}") from exc


def validate_source_artifacts(source: ReviewSource) -> None:
    root = Path(source.run_path)
    for name, digest in source.files.items():
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()):
            raise SourceArtifactError(
                "invalid", f"Review source artifact is outside its run: {path}"
            )
        if not path.is_file():
            raise SourceArtifactError("missing", f"Review source artifact is missing: {path}")
        if hash_file(path) != digest:
            raise SourceArtifactError("changed", f"Review source artifact changed: {path}")
