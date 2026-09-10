"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/publication/record.py

Defines private preparation snapshots and their deterministic serialization.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StringConstraints,
    field_validator,
    model_validator,
)

Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class FileStamp(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    path: str
    sha256: Digest

    @field_validator("path")
    @classmethod
    def absolute_path(cls, value: str) -> str:
        if not Path(value).is_absolute():
            raise ValueError("Preparation paths must be absolute")
        return value


class _VersionedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal[1]

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("Publication record schema_version must be the integer 1")
        return value


class PreparationRecord(_VersionedRecord):
    variant: str
    authored_source: FileStamp
    exported_pdf: FileStamp
    policy: FileStamp
    variant_config: FileStamp
    person: FileStamp
    pdf_sha256: Digest
    manifest_sha256: Digest
    review_files: dict[str, Digest]

    @model_validator(mode="after")
    def matching_packet_pdf(self) -> Self:
        if self.review_files.get("cv.pdf") != self.pdf_sha256:
            raise ValueError("Review packet must identify the exact prepared PDF")
        return self

    @field_validator("review_files")
    @classmethod
    def packet_filenames(cls, value: dict[str, str]) -> dict[str, str]:
        if not {"cv.pdf", "review.html", "review.json"}.issubset(value):
            raise ValueError("Preparation must identify the complete review packet")
        if any(Path(name).name != name or name in {".", ".."} for name in value):
            raise ValueError("Review packet entries must be filenames")
        return value


class ReviewReceipt(_VersionedRecord):
    pdf_sha256: Digest
    preparation_sha256: Digest
    reviewed_at: AwareDatetime


def hash_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def stamp_file(path: Path) -> FileStamp:
    return FileStamp(path=str(path.resolve()), sha256=hash_file(path))


def json_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def preparation_bytes(
    *,
    authored_source: Path,
    source_pdf: Path,
    policy_path: Path,
    variant_path: Path,
    person_path: Path,
    variant: str,
    pdf_hash: str,
    manifest_content: str,
    review_files: dict[str, bytes],
    authored_hash: str,
    exported_hash: str,
) -> bytes:
    source = stamp_file(authored_source)
    export = stamp_file(source_pdf)
    if source.sha256 != authored_hash or export.sha256 != exported_hash:
        raise ValueError("Authored inputs changed during preparation; export and prepare again")
    record = PreparationRecord(
        schema_version=1,
        variant=variant,
        authored_source=source,
        exported_pdf=export,
        policy=stamp_file(policy_path),
        variant_config=stamp_file(variant_path),
        person=stamp_file(person_path),
        pdf_sha256=pdf_hash,
        manifest_sha256=hashlib.sha256(manifest_content.encode()).hexdigest(),
        review_files={
            name: hashlib.sha256(content).hexdigest() for name, content in review_files.items()
        },
    )
    return json_bytes(record.model_dump())
