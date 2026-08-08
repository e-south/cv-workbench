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
from cvworkbench.ops.publish import PublishError, load_publish_config
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
    assert manifest["source"]["pdf_token_coverage"] >= 0.9
    assert manifest["source"]["docx_token_coverage"] >= 0.9
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


def test_prepare_public_pdf_redacts_compact_phone_matching_source_of_truth(
    tmp_path: Path,
) -> None:
    config_path, _, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "authored.pdf"
    authored_source = tmp_path / "authored.docx"
    _write_docx(authored_source, "Example Person 5558675309 Education")
    _write_pdf(source_pdf, ["Example Person | 5558675309\nEducation"])

    result = prepare_public_pdf(
        authored_source=authored_source,
        source_pdf=source_pdf,
        config_path=config_path,
        variant_id="base",
        publish_config_path=publish_path,
        sot_path=sot_path,
    )

    with pymupdf.open(result.output_pdf) as document:
        assert "5558675309" not in "\n".join(page.get_text() for page in document)


def test_validate_public_pdf_rejects_hidden_contact_link(tmp_path: Path) -> None:
    _, variant_path, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "unsafe-link.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Example Person")
    page.insert_link(
        {
            "kind": pymupdf.LINK_URI,
            "from": pymupdf.Rect(72, 100, 180, 112),
            "uri": "mailto:advisor@example.org",
        }
    )
    document.save(source_pdf)
    document.close()

    with pytest.raises(PublicPdfError, match="unsafe or hidden link"):
        validate_public_pdf(
            source_pdf,
            variant=load_variant(variant_path),
            publish=load_publish_config(publish_path),
            sot_path=sot_path,
        )


def test_validate_public_pdf_accepts_visible_https_link(tmp_path: Path) -> None:
    _, variant_path, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "safe-link.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Profile")
    link_rect = page.search_for("Profile")[0]
    page.insert_link(
        {
            "kind": pymupdf.LINK_URI,
            "from": link_rect,
            "uri": "https://example.com/profile",
        }
    )
    document.save(source_pdf)
    document.close()

    validate_public_pdf(
        source_pdf,
        variant=load_variant(variant_path),
        publish=load_publish_config(publish_path),
        sot_path=sot_path,
    )


def test_prepare_public_pdf_rejects_truncated_export(tmp_path: Path) -> None:
    config_path, _, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "truncated.pdf"
    authored_source = tmp_path / "authored.docx"
    _write_docx(
        authored_source,
        "Example Person Education Research Publications Teaching Service Honors "
        "Experience Skills Projects Conferences Awards Affiliations Summary",
    )
    _write_pdf(source_pdf, ["Example Person"])

    with pytest.raises(PublicPdfError, match="does not correspond closely enough"):
        prepare_public_pdf(
            authored_source=authored_source,
            source_pdf=source_pdf,
            config_path=config_path,
            variant_id="base",
            publish_config_path=publish_path,
            sot_path=sot_path,
        )


def test_publish_config_rejects_unsupported_forbidden_contact_field(tmp_path: Path) -> None:
    _, _, publish_path, _ = _write_workspace(tmp_path)
    publish_path.write_text(
        publish_path.read_text().replace(
            "forbidden_contact_fields: [phone]",
            "forbidden_contact_fields: [phone, location]",
        )
    )

    with pytest.raises(PublishError, match="unsupported forbidden contact fields: location"):
        load_publish_config(publish_path)


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


def test_validate_public_pdf_layout_rejects_unapproved_text_deletion(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    public_pdf = tmp_path / "public.pdf"
    _write_pdf(source_pdf, ["Example Person"])

    document = pymupdf.open(source_pdf)
    page = document[0]
    page.add_redact_annot(page.search_for("Person")[0], fill=(1, 1, 1), cross_out=False)
    page.apply_redactions(images=0, graphics=0, text=0)
    document.save(public_pdf)
    document.close()

    with pytest.raises(PublicPdfError, match="unapproved removal"):
        validate_public_pdf_layout(source_pdf, public_pdf)


def test_prepare_public_pdf_anchors_redaction_to_exact_section_heading(
    tmp_path: Path,
) -> None:
    config_path, _, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "authored.pdf"
    authored_source = tmp_path / "authored.docx"
    text = (
        "Example Person References appear in this prose Public retained line "
        "References Advisor advisor@example.org"
    )
    _write_docx(authored_source, text)
    _write_pdf(
        source_pdf,
        [
            "Example Person\nReferences appear in this prose.\nPublic retained line\n"
            "References\nAdvisor | advisor@example.org"
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

    with pymupdf.open(result.output_pdf) as document:
        public_text = "\n".join(page.get_text() for page in document)
    assert "References appear in this prose." in public_text
    assert "Public retained line" in public_text
    assert "Advisor" not in public_text


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
