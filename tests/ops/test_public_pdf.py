"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_public_pdf.py

Tests faithful authored-PDF publication and privacy validation.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pymupdf
import pytest
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.ops.public_pdf import (
    PublicPdfError,
    prepare_public_pdf,
    validate_public_pdf,
    validate_public_pdf_layout,
)
from cvworkbench.ops.publish import load_publish_config
from cvworkbench.variants import load_variant


def _write_pdf(path: Path, pages: list[str]) -> None:
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        page.insert_text((72, 72), text, fontsize=11)
    document.save(path)
    document.close()


def _write_docx(path: Path, text: str) -> None:
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>"
        "</w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)


def _write_workspace(root: Path) -> tuple[Path, Path, Path, Path]:
    (root / "config/variants").mkdir(parents=True)
    (root / "local/sot").mkdir(parents=True)
    config_path = root / "config/workbench.yaml"
    config_path.write_text(
        "paths:\n  sot: ../local/sot\n  dist: ../var/dist\nvariants:\n  default: base\n"
    )
    variant_path = root / "config/variants/base.yaml"
    variant_path.write_text(
        "variant:\n"
        "  id: base\n"
        "  exclude_tags: [private]\n"
        "  contact_fields: [email, location, links]\n"
        "  order: [summary, experience, education]\n"
        "  outputs: [pdf]\n"
    )
    publish_path = root / "config/publish.yaml"
    publish_path.write_text(
        "publish:\n"
        "  variants: [base]\n"
        "  required_exclude_tags: [private]\n"
        "  forbidden_contact_fields: [phone]\n"
        "  forbidden_sections: [references]\n"
    )
    person_path = root / "local/sot/person.yaml"
    person_path.write_text(
        "id: person\n"
        "name: Example Person\n"
        "email: person@example.com\n"
        "phone: 555.867.5309\n"
        "location:\n"
        "  city: Boston\n"
    )
    return config_path, variant_path, publish_path, person_path.parent


def test_prepare_public_pdf_preserves_content_and_removes_private_surfaces(
    tmp_path: Path,
) -> None:
    config_path, variant_path, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "authored.pdf"
    authored_source = tmp_path / "authored.docx"
    _write_docx(
        authored_source,
        "Example Person 555.867.5309 person@example.com Education Research "
        "Publications References Advisor advisor@example.org",
    )
    _write_pdf(
        source_pdf,
        [
            "Example Person | 555.867.5309 | person@example.com\nEducation\nResearch",
            "Publications\nReferences\nAdvisor | advisor@example.org",
        ],
    )

    result = prepare_public_pdf(
        authored_source=authored_source,
        source_pdf=source_pdf,
        config_path=config_path,
        variant_id="base",
        publish_config_path=publish_path,
        sot_path=sot_path,
    )

    assert result.output_pdf == tmp_path / "var/publish/base/cv.pdf"
    document = pymupdf.open(result.output_pdf)
    text = "\n".join(page.get_text() for page in document)
    document.close()
    assert "Example Person" in text
    assert "Education" in text
    assert "Publications" in text
    assert "555.867.5309" not in text
    assert "References" not in text
    assert "advisor@example.org" not in text

    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["artifact_kind"] == "authored-pdf-publication"
    assert manifest["variant"]["contact_fields"] == ["email", "location", "links"]
    assert manifest["outputs"] == {"pdf": "cv.pdf"}
    assert (
        manifest["output_hashes"]["pdf"]
        == hashlib.sha256(result.output_pdf.read_bytes()).hexdigest()
    )
    assert manifest["source"]["authored_name"] == "authored.docx"
    assert manifest["source"]["exported_pdf_name"] == "authored.pdf"
    assert manifest["source"]["text_token_coverage"] >= 0.9
    assert "phone" in manifest["transformation"]["forbidden_contact_fields"]

    first_bytes = result.output_pdf.read_bytes()
    second_result = prepare_public_pdf(
        authored_source=authored_source,
        source_pdf=source_pdf,
        config_path=config_path,
        variant_id="base",
        publish_config_path=publish_path,
        sot_path=sot_path,
    )
    assert second_result.output_pdf.read_bytes() == first_bytes


def test_validate_public_pdf_rejects_unauthorized_third_party_email(tmp_path: Path) -> None:
    _, variant_path, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "unsafe.pdf"
    _write_pdf(source_pdf, ["Example Person\nperson@example.com\nadvisor@example.org"])

    with pytest.raises(PublicPdfError, match="unauthorized email"):
        validate_public_pdf(
            source_pdf,
            variant=load_variant(variant_path),
            publish=load_publish_config(publish_path),
            sot_path=sot_path,
        )


def test_validate_public_pdf_layout_rejects_moved_surviving_text(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    public_pdf = tmp_path / "public.pdf"
    _write_pdf(source_pdf, ["Example Person"])

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((80, 72), "Example Person", fontsize=11)
    document.save(public_pdf)
    document.close()

    with pytest.raises(PublicPdfError, match="layout drift"):
        validate_public_pdf_layout(source_pdf, public_pdf)


def test_prepare_public_pdf_fails_closed_when_required_heading_cannot_be_redacted(
    tmp_path: Path,
) -> None:
    config_path, _, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "unsafe.pdf"
    authored_source = tmp_path / "authored.docx"
    _write_docx(authored_source, "References to prior research are discussed here.")
    _write_pdf(source_pdf, ["References to prior research are discussed here."])

    with pytest.raises(PublicPdfError, match="forbidden section heading"):
        prepare_public_pdf(
            authored_source=authored_source,
            source_pdf=source_pdf,
            config_path=config_path,
            variant_id="base",
            publish_config_path=publish_path,
            sot_path=sot_path,
        )


def test_prepare_public_pdf_cli_exposes_artifact_and_manifest(tmp_path: Path) -> None:
    config_path, _, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "authored.pdf"
    authored_source = tmp_path / "authored.docx"
    _write_docx(authored_source, "Example Person person@example.com Education")
    _write_pdf(source_pdf, ["Example Person | person@example.com\nEducation"])

    result = CliRunner().invoke(
        app,
        [
            "prepare-public-pdf",
            "--authored-source",
            str(authored_source),
            "--source-pdf",
            str(source_pdf),
            "--config",
            str(config_path),
            "--publish-config",
            str(publish_path),
            "--sot-path",
            str(sot_path),
            "--plain",
        ],
    )

    assert result.exit_code == 0
    assert "output_pdf:" in result.stdout
    assert "manifest:" in result.stdout
    assert (tmp_path / "var/publish/base/cv.pdf").exists()
