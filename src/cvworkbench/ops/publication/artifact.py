"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/publication/artifact.py

Validates publication provenance and policy independently of site transport.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from cvworkbench.ops.publication.manifest import parse_publication_manifest
from cvworkbench.ops.publication.policy import PublishConfig
from cvworkbench.variants import Variant


class PublicationArtifactError(ValueError):
    pass


@dataclass(frozen=True)
class PublicArtifact:
    source: Path
    content: bytes = field(repr=False)
    sha256: str


def validate_publish_policy(variant: Variant, publish: PublishConfig) -> None:
    missing_tags = sorted(set(publish.required_exclude_tags) - set(variant.exclude_tags))
    if missing_tags:
        raise PublicationArtifactError(
            f"Publish variant is missing required exclude tags: {', '.join(missing_tags)}"
        )

    contact_fields = sorted(set(variant.contact_fields) & set(publish.forbidden_contact_fields))
    if contact_fields:
        raise PublicationArtifactError(
            f"Publish variant includes forbidden contact fields: {', '.join(contact_fields)}"
        )

    sections = sorted(set(variant.order) & set(publish.forbidden_sections))
    if sections:
        raise PublicationArtifactError(
            f"Publish variant includes forbidden sections: {', '.join(sections)}"
        )


def validate_public_artifact(
    source_pdf: Path,
    manifest_path: Path,
    variant: Variant,
    publish: PublishConfig,
) -> str:
    return read_public_artifact(source_pdf, manifest_path, variant, publish).sha256


def read_public_artifact(
    source_pdf: Path,
    manifest_path: Path,
    variant: Variant,
    publish: PublishConfig,
) -> PublicArtifact:
    """Capture PDF bytes and verify their identity against publication provenance."""
    content = source_pdf.read_bytes()
    if not content.startswith(b"%PDF-"):
        raise PublicationArtifactError(f"Public artifact is not a PDF: {source_pdf}")
    if not manifest_path.exists():
        raise PublicationArtifactError(f"Build manifest not found: {manifest_path}")
    try:
        manifest = parse_publication_manifest(manifest_path.read_text())
    except (OSError, ValueError) as exc:
        raise PublicationArtifactError(f"Build manifest is invalid: {exc}") from exc
    if manifest.variant.id != variant.id:
        raise PublicationArtifactError("Build manifest variant does not match publish variant")
    variant_contract = {
        "exclude_tags": variant.exclude_tags,
        "contact_fields": variant.contact_fields,
        "order": variant.order,
    }
    for key, expected in variant_contract.items():
        if getattr(manifest.variant, key) != expected:
            raise PublicationArtifactError(f"Build manifest {key} does not match publish variant")

    if manifest.outputs.pdf != source_pdf.name:
        raise PublicationArtifactError("Build manifest does not declare the PDF artifact")
    pdf_hash = hashlib.sha256(content).hexdigest()
    if manifest.output_hashes.pdf != pdf_hash:
        raise PublicationArtifactError("Build manifest PDF hash does not match the artifact")
    if manifest.source.visual_fingerprint_sha256 != publish.approved_visual_fingerprint_sha256:
        raise PublicationArtifactError(
            "Build manifest visual fingerprint does not match publish policy"
        )
    if manifest.transformation.forbidden_contact_fields != publish.forbidden_contact_fields:
        raise PublicationArtifactError(
            "Build manifest contact policy does not match publish policy"
        )
    if manifest.transformation.forbidden_sections != publish.forbidden_sections:
        raise PublicationArtifactError(
            "Build manifest section policy does not match publish policy"
        )
    return PublicArtifact(source=source_pdf, content=content, sha256=pdf_hash)
