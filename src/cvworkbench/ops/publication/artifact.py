"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/publication/artifact.py

Validates publication provenance and policy independently of site transport.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path

from cvworkbench.ops.publication.policy import PublishConfig
from cvworkbench.ops.publication.record import hash_file
from cvworkbench.variants import Variant


class PublicationArtifactError(ValueError):
    pass


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
    if not source_pdf.read_bytes().startswith(b"%PDF-"):
        raise PublicationArtifactError(f"Public artifact is not a PDF: {source_pdf}")
    if not manifest_path.exists():
        raise PublicationArtifactError(f"Build manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise PublicationArtifactError(f"Build manifest is invalid: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise PublicationArtifactError(f"Build manifest is invalid: {manifest_path}")
    if manifest.get("schema_version") != 1:
        raise PublicationArtifactError(
            "Build manifest schema does not match authored publication contract"
        )
    if manifest.get("artifact_kind") != "authored-pdf-publication":
        raise PublicationArtifactError("Build manifest is not an authored PDF publication")
    if manifest.get("formats") != ["pdf"]:
        raise PublicationArtifactError(
            "Build manifest must declare only the PDF publication format"
        )

    manifest_variant = manifest.get("variant")
    if not isinstance(manifest_variant, dict) or manifest_variant.get("id") != variant.id:
        raise PublicationArtifactError("Build manifest variant does not match publish variant")
    variant_contract = {
        "exclude_tags": variant.exclude_tags,
        "contact_fields": variant.contact_fields,
        "order": variant.order,
    }
    for key, expected in variant_contract.items():
        if manifest_variant.get(key) != expected:
            raise PublicationArtifactError(f"Build manifest {key} does not match publish variant")

    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict) or outputs.get("pdf") != source_pdf.name:
        raise PublicationArtifactError("Build manifest does not declare the PDF artifact")
    output_hashes = manifest.get("output_hashes")
    pdf_hash = hash_file(source_pdf)
    if not isinstance(output_hashes, dict) or output_hashes.get("pdf") != pdf_hash:
        raise PublicationArtifactError("Build manifest PDF hash does not match the artifact")
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise PublicationArtifactError("Build manifest lacks authored source provenance")
    transformation = manifest.get("transformation")
    if not isinstance(transformation, dict) or transformation.get("kind") != "semantic-redaction":
        raise PublicationArtifactError(
            "Build manifest lacks the semantic-redaction provenance contract"
        )
    redaction_count = transformation.get("redaction_count")
    if not isinstance(redaction_count, int) or isinstance(redaction_count, bool):
        raise PublicationArtifactError("Build manifest redaction count is invalid")
    if source.get("visual_fingerprint_sha256") != publish.approved_visual_fingerprint_sha256:
        raise PublicationArtifactError(
            "Build manifest visual fingerprint does not match publish policy"
        )
    if transformation.get("forbidden_contact_fields") != publish.forbidden_contact_fields:
        raise PublicationArtifactError(
            "Build manifest contact policy does not match publish policy"
        )
    if transformation.get("forbidden_sections") != publish.forbidden_sections:
        raise PublicationArtifactError(
            "Build manifest section policy does not match publish policy"
        )
    return pdf_hash
