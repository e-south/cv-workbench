"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/publication/manifest.py

Defines the authored publication provenance schema and its strict JSON boundary.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

from cvworkbench.ops.publication.policy import PublishConfig
from cvworkbench.variants import Variant

Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Coverage = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class _ManifestFields(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def _filename(value: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or Path(value).name != value
        or any(character in value for character in ("/", "\\", "\n", "\r", "\0"))
    ):
        raise ValueError("Publication names must be single filenames")
    return value


class PublicationVariant(_ManifestFields):
    id: Annotated[str, StringConstraints(min_length=1)]
    exclude_tags: list[str]
    contact_fields: list[str]
    order: list[str]


class PdfOutput(_ManifestFields):
    pdf: str

    _pdf_filename = field_validator("pdf")(_filename)


class PdfDigest(_ManifestFields):
    pdf: Digest


class AuthoredSource(_ManifestFields):
    authored_name: str
    authored_sha256: Digest
    exported_pdf_name: str
    exported_pdf_sha256: Digest
    pdf_token_coverage: Coverage
    docx_token_coverage: Coverage
    visual_fingerprint_sha256: Digest

    _source_filenames = field_validator("authored_name", "exported_pdf_name")(_filename)


class PublicationTransformation(_ManifestFields):
    kind: Literal["semantic-redaction"]
    forbidden_contact_fields: list[str]
    forbidden_sections: list[str]
    redaction_count: Annotated[int, Field(ge=0)]


class _PublicationManifest(_ManifestFields):
    schema_version: Literal[1]
    variant: PublicationVariant
    formats: Annotated[list[Literal["pdf"]], Field(min_length=1, max_length=1)]
    outputs: PdfOutput
    output_hashes: PdfDigest

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("schema_version must be the integer 1")
        return value


class PublicationManifest(_PublicationManifest):
    artifact_kind: Literal["authored-pdf-publication"]
    source: AuthoredSource
    transformation: PublicationTransformation


class NativeSource(_ManifestFields):
    run_manifest_sha256: Digest
    rendered_markdown_sha256: Digest
    exported_pdf_sha256: Digest
    visual_fingerprint_sha256: Digest
    allowed_links: list[str]


class NativeTransformation(_ManifestFields):
    kind: Literal["native-sanitization"]
    forbidden_contact_fields: list[str]
    forbidden_sections: list[str]
    redaction_count: Annotated[int, Field(ge=0, le=0)]


class NativePublicationManifest(_PublicationManifest):
    artifact_kind: Literal["native-pdf-publication"]
    source: NativeSource
    transformation: NativeTransformation


def parse_publication_manifest(content: str) -> PublicationManifest | NativePublicationManifest:
    payload = json.loads(content, object_pairs_hook=_unique_fields)
    kind = payload.get("artifact_kind") if isinstance(payload, dict) else None
    if kind not in {"authored-pdf-publication", "native-pdf-publication"}:
        raise ValueError("Build manifest is not an authored PDF publication")
    try:
        model = (
            NativePublicationManifest if kind == "native-pdf-publication" else PublicationManifest
        )
        return model.model_validate(payload)
    except ValidationError as exc:
        messages = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_input=False)
        )
        raise ValueError(f"Build manifest schema is invalid: {messages}") from exc


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"Build manifest contains a duplicate field: {key}")
        payload[key] = value
    return payload


def publication_manifest_content(
    *,
    authored_name: str,
    authored_sha256: str,
    source_pdf_name: str,
    source_pdf_sha256: str,
    output_pdf_name: str,
    output_pdf_sha256: str,
    variant: Variant,
    publish: PublishConfig,
    redaction_count: int,
    pdf_token_coverage: float,
    docx_token_coverage: float,
    source_visual_fingerprint: str,
) -> str:
    payload = {
        "schema_version": 1,
        "artifact_kind": "authored-pdf-publication",
        "variant": {
            "id": variant.id,
            "exclude_tags": list(variant.exclude_tags),
            "contact_fields": list(variant.contact_fields),
            "order": list(variant.order),
        },
        "formats": ["pdf"],
        "outputs": {"pdf": output_pdf_name},
        "output_hashes": {"pdf": output_pdf_sha256},
        "source": {
            "authored_name": authored_name,
            "authored_sha256": authored_sha256,
            "exported_pdf_name": source_pdf_name,
            "exported_pdf_sha256": source_pdf_sha256,
            "pdf_token_coverage": round(pdf_token_coverage, 6),
            "docx_token_coverage": round(docx_token_coverage, 6),
            "visual_fingerprint_sha256": source_visual_fingerprint,
        },
        "transformation": {
            "kind": "semantic-redaction",
            "forbidden_contact_fields": list(publish.forbidden_contact_fields),
            "forbidden_sections": list(publish.forbidden_sections),
            "redaction_count": redaction_count,
        },
    }
    manifest = PublicationManifest.model_validate(payload)
    return json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
