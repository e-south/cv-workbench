"""Private document identities, explicit promotion requests, and receipt chains."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DocumentError(ValueError):
    pass


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Identity(Model):
    id: Identifier
    kind: Text
    edition: Text
    audience: Literal["application", "private", "public"]


class AuthoredSource(Model):
    kind: Literal["authored"]
    path: Text


class NativeSource(Model):
    kind: Literal["native"]
    config: Text
    path: Text
    variant: Identifier
    run: Text


class PublicationSource(Model):
    kind: Literal["publication"]
    config: Text
    variant: Identifier


class Transfer(Model):
    source: Text
    destination: Text


class PromotionRequest(Model):
    schema_version: Literal[1]
    document: Identity
    source: Annotated[
        AuthoredSource | NativeSource | PublicationSource, Field(discriminator="kind")
    ]
    files: list[Transfer] = Field(min_length=1)
    replace_modified_current: bool = False


class SourceEvidence(Model):
    kind: Literal["authored", "native", "publication"]
    path: Text
    configuration: Text | None = None
    variant: Text | None = None
    run_path: Text | None = None
    stamps: dict[str, Digest]


class ArtifactSnapshot(Model):
    source: Text
    destination: Text
    sha256: Digest
    previous_sha256: Digest | None


class RetiredFile(Model):
    destination: Text
    sha256: Digest


class PlanData(Model):
    schema_version: Literal[1]
    root: Text
    request_path: Text
    request_sha256: Digest
    document: Identity
    source: SourceEvidence
    files: list[ArtifactSnapshot] = Field(min_length=1)
    retired_files: list[RetiredFile]
    previous_receipt: Text | None
    history: dict[str, Digest]


class ArchivedFile(Model):
    destination: Text
    archive: Text
    sha256: Digest


class Receipt(Model):
    schema_version: Literal[1]
    plan: PlanData
    plan_sha256: Digest
    promoted_at: Text
    previous_files: list[ArchivedFile]


def encode(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_json(content: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise DocumentError("Duplicate field in document record")
            result[key] = value
        return result

    try:
        result = json.loads(content, object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise DocumentError("Invalid document JSON record") from exc
    if not isinstance(result, dict) or type(result.get("schema_version")) is not int:
        raise DocumentError("Document record requires an integer schema_version")
    return result


def regular_path(path: Path, *, missing: bool = False) -> Path:
    path = path.absolute()
    if any(part.is_symlink() for part in [path, *path.parents]):
        raise DocumentError(f"Document paths cannot traverse symlinks: {path}")
    if path.exists() and not path.is_file():
        raise DocumentError(f"Expected a regular document file: {path}")
    if not missing and not path.is_file():
        raise DocumentError(f"Missing document file: {path}")
    return path.resolve()


def library_path(root: Path, value: str, area: str) -> Path:
    relative = Path(value)
    if str(relative) != value:
        raise DocumentError("Document destinations require canonical relative paths")
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or not relative.parts
        or relative.parts[0] != area
    ):
        raise DocumentError(f"Document destination must remain beneath {area}")
    if len(relative.parts) < 2:
        raise DocumentError("Document destination must name a file")
    return regular_path(root / relative, missing=True)


def load_receipts(root: Path) -> tuple[dict[str, dict], dict[str, bytes]]:
    """Return one unambiguous chain tip per identity; never select by mtime."""
    store = root / "records/promotions"
    if store.is_symlink():
        raise DocumentError("Promotion store cannot be a symlink")
    records, contents, predecessors = {}, {}, set()
    for path in sorted(store.glob("*/*.json")):
        content = regular_path(path).read_bytes()
        raw = read_json(content)
        try:
            receipt = Receipt.model_validate(raw)
            record = receipt.plan.model_dump()
            identity = receipt.plan.document
            if (
                receipt.plan_sha256 != path.stem
                or identity.id != path.parent.name
                or record["root"] != str(root)
            ):
                raise ValueError
            if digest(encode(record)) != receipt.plan_sha256:
                raise ValueError
            if len({f["destination"] for f in record["files"]}) != len(record["files"]):
                raise ValueError
            for item in record["files"]:
                library_path(root, item["destination"], "current")
            for item in receipt.previous_files:
                library_path(root, item.archive, "archive")
            previous = record["previous_receipt"]
            if previous is not None:
                library_path(root, previous, "records")
                predecessors.add(previous)
        except (ValueError, KeyError, TypeError) as exc:
            raise DocumentError(f"Invalid promotion receipt: {path}") from exc
        relative = str(path.relative_to(root))
        records[relative], contents[relative] = (
            {**record, "previous_files": raw["previous_files"]},
            content,
        )
    if predecessors - records.keys():
        raise DocumentError("Promotion history has a missing predecessor")
    for record in records.values():
        previous = record["previous_receipt"]
        if previous is not None and records[previous]["document"]["id"] != record["document"]["id"]:
            raise DocumentError("Promotion predecessor belongs to another identity")
    tips = {}
    for path in records.keys() - predecessors:
        record = records[path]
        identifier = record["document"]["id"]
        if identifier in tips:
            raise DocumentError("Conflicting promotion history for document identity")
        tips[identifier] = {**record, "receipt_path": path}
    if records and len(tips) != len({r["document"]["id"] for r in records.values()}):
        raise DocumentError("Promotion history contains a cycle")
    return tips, contents
