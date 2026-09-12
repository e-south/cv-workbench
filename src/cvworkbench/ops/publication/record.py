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


class PreparationInputChangedError(ValueError):
    pass


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


class PreparationInputs(BaseModel):
    """Original identities and hashes of the input bytes used for preparation."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    authored_source: FileStamp
    exported_pdf: FileStamp
    policy: FileStamp
    variant_config: FileStamp
    person: FileStamp


class _PreparationRecord(_VersionedRecord):
    variant: str
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


class PreparationRecord(_PreparationRecord):
    authored_source: FileStamp


class NativePreparationRecord(_PreparationRecord):
    kind: Literal["native-build"]
    configuration: FileStamp
    run_manifest: FileStamp
    rendered_markdown: FileStamp
    rendered_html: FileStamp | None = None
    html_stylesheet: FileStamp | None = None
    source_files: dict[str, FileStamp]


def parse_preparation_record(content: bytes) -> PreparationRecord | NativePreparationRecord:
    payload = json.loads(content)
    model = (
        NativePreparationRecord
        if isinstance(payload, dict) and payload.get("kind") == "native-build"
        else PreparationRecord
    )
    return model.model_validate(payload)


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
    inputs: PreparationInputs,
    variant: str,
    pdf_hash: str,
    manifest_content: str,
    review_files: dict[str, bytes],
) -> bytes:
    for name in PreparationInputs.model_fields:
        captured = getattr(inputs, name)
        try:
            current = stamp_file(Path(captured.path))
        except OSError as exc:
            raise PreparationInputChangedError(
                f"Publication inputs changed during preparation ({name}); prepare again"
            ) from exc
        if current != captured:
            raise PreparationInputChangedError(
                f"Publication inputs changed during preparation ({name}); prepare again"
            )
    record = PreparationRecord(
        schema_version=1,
        variant=variant,
        authored_source=inputs.authored_source,
        exported_pdf=inputs.exported_pdf,
        policy=inputs.policy,
        variant_config=inputs.variant_config,
        person=inputs.person,
        pdf_sha256=pdf_hash,
        manifest_sha256=hashlib.sha256(manifest_content.encode()).hexdigest(),
        review_files={
            name: hashlib.sha256(content).hexdigest() for name, content in review_files.items()
        },
    )
    return json_bytes(record.model_dump())
