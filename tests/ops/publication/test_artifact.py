"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/publication/test_artifact.py

Tests authored publication identity and manifest eligibility at the artifact boundary.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import hashlib
import json
from pathlib import Path

import pytest

from cvworkbench.ops.publication.artifact import PublicationArtifactError, validate_public_artifact
from cvworkbench.ops.publication.policy import load_publish_config
from cvworkbench.variants import load_variant
from tests.ops.publication.test_pdf import _write_pdf
from tests.ops.publication.test_state import _prepare


def test_artifact_signature_and_hash_describe_the_same_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _, _, policy, _ = _prepare(tmp_path)
    pdf = tmp_path / "var/publish/base/cv.pdf"
    manifest = pdf.with_name("manifest.json")
    changed = b"This is not a PDF"
    data = json.loads(manifest.read_text())
    data["output_hashes"]["pdf"] = hashlib.sha256(changed).hexdigest()
    manifest.write_text(json.dumps(data))
    original_read = Path.read_bytes

    def change_after_read(path):
        content = original_read(path)
        if path == pdf:
            path.write_bytes(changed)
        return content

    monkeypatch.setattr(Path, "read_bytes", change_after_read)
    with pytest.raises(PublicationArtifactError, match="PDF hash does not match"):
        validate_public_artifact(
            pdf,
            manifest,
            load_variant(config.parent / "variants/base.yaml"),
            load_publish_config(policy),
        )


def test_captured_pdf_is_validated_without_reopening_its_source(tmp_path: Path) -> None:
    from cvworkbench.ops.publication.artifact import read_public_artifact
    from cvworkbench.ops.publication.pdf import PublicPdfError, validate_public_pdf_content

    config, _, _, policy_path, sot = _prepare(tmp_path)
    pdf = tmp_path / "var/publish/base/cv.pdf"
    variant = load_variant(config.parent / "variants/base.yaml")
    policy = load_publish_config(policy_path)
    artifact = read_public_artifact(pdf, pdf.with_name("manifest.json"), variant, policy)
    pdf.unlink()

    validate_public_pdf_content(artifact.content, variant=variant, publish=policy, sot_path=sot)
    private_pdf = tmp_path / "private.pdf"
    _write_pdf(private_pdf, ["Private contact: unauthorized@example.org"])
    with pytest.raises(PublicPdfError, match="unauthorized email"):
        validate_public_pdf_content(
            private_pdf.read_bytes(), variant=variant, publish=policy, sot_path=sot
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 1.0),
        ("transformation.redaction_count", -1),
        ("source.authored_name", "../private/master.docx"),
        ("source.exported_pdf_name", "/private/export.pdf"),
        ("source.authored_sha256", "unknown"),
        ("source.exported_pdf_sha256", None),
        ("source.pdf_token_coverage", -0.1),
        ("source.docx_token_coverage", 1.1),
        ("source.pdf_token_coverage", float("nan")),
        ("source.pdf_token_coverage", "0.95"),
        ("outputs.docx", "private.docx"),
        ("private_source_path", "/private/master.docx"),
    ],
)
def test_publication_manifest_rejects_invalid_or_undeclared_fields(tmp_path, field, value):
    config, _, _, policy, _ = _prepare(tmp_path)
    pdf = tmp_path / "var/publish/base/cv.pdf"
    manifest = pdf.with_name("manifest.json")
    data = json.loads(manifest.read_text())
    target = data
    parts = field.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    manifest.write_text(json.dumps(data))

    with pytest.raises(PublicationArtifactError, match="Build manifest"):
        validate_public_artifact(
            pdf,
            manifest,
            load_variant(config.parent / "variants/base.yaml"),
            load_publish_config(policy),
        )


@pytest.mark.parametrize(
    "original,replacement",
    [
        ('"schema_version": 1', '"schema_version": false, "schema_version": 1'),
        ('"pdf": "cv.pdf"', '"pdf": "private.pdf", "pdf": "cv.pdf"'),
    ],
)
def test_publication_manifest_rejects_ambiguous_duplicate_fields(tmp_path, original, replacement):
    config, _, _, policy, _ = _prepare(tmp_path)
    pdf = tmp_path / "var/publish/base/cv.pdf"
    manifest = pdf.with_name("manifest.json")
    text = manifest.read_text()
    assert original in text
    manifest.write_text(text.replace(original, replacement, 1))

    with pytest.raises(PublicationArtifactError, match="duplicate field"):
        validate_public_artifact(
            pdf,
            manifest,
            load_variant(config.parent / "variants/base.yaml"),
            load_publish_config(policy),
        )
