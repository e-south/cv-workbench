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
from cvworkbench.ops import atomic
from cvworkbench.ops.public_pdf import (
    PHONE_CANDIDATE_PATTERN,
    PublicPdfError,
    _matches_forbidden_phone,
    _visual_fingerprint,
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
        "  approved_visual_fingerprint_sha256: "
        "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945\n"
    )
    person_path = root / "local/sot/person.yaml"
    person_path.write_text(
        "id: person\n"
        "name: Example Person\n"
        "email: person@example.com\n"
        "phone: 555.867.5309\n"
        "links:\n"
        "  - label: Profile\n"
        "    url: https://example.com/profile\n"
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
    assert manifest["source"]["visual_fingerprint_sha256"] == (
        "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
    )
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


def test_validate_public_pdf_rejects_third_party_phone(tmp_path: Path) -> None:
    _, variant_path, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "unsafe.pdf"
    _write_pdf(source_pdf, ["Example Person\nAdvisor | 212.555.0199"])

    with pytest.raises(PublicPdfError, match="forbidden phone number"):
        validate_public_pdf(
            source_pdf,
            variant=load_variant(variant_path),
            publish=load_publish_config(publish_path),
            sot_path=sot_path,
        )


@pytest.mark.parametrize("separator", [" ", "‐", "‑", "–", "—", " ", "−"])
def test_phone_candidate_pattern_recognizes_typographic_separators(
    separator: str,
) -> None:
    candidate = f"212{separator}555{separator}0199"

    assert PHONE_CANDIDATE_PATTERN.fullmatch(candidate)
    assert _matches_forbidden_phone(candidate, ("5558675309",))


def test_validate_public_pdf_rejects_extracted_typographic_dash_phone(
    tmp_path: Path,
) -> None:
    _, variant_path, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "unsafe.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Advisor | 212–555–0199", fontname="china-s")
    document.save(source_pdf)
    document.close()

    with pytest.raises(PublicPdfError, match="forbidden phone number"):
        validate_public_pdf(
            source_pdf,
            variant=load_variant(variant_path),
            publish=load_publish_config(publish_path),
            sot_path=sot_path,
        )


def test_validate_public_pdf_does_not_treat_citation_numbers_as_phones(
    tmp_path: Path,
) -> None:
    _, variant_path, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "safe.pdf"
    _write_pdf(
        source_pdf,
        ["Nat Chem Biol 19, 951-961 (2023)\nACS Omega 2022 7 (22), 18331-18338"],
    )

    validate_public_pdf(
        source_pdf,
        variant=load_variant(variant_path),
        publish=load_publish_config(publish_path),
        sot_path=sot_path,
    )


def test_validate_public_pdf_does_not_treat_compact_isbns_as_phones(
    tmp_path: Path,
) -> None:
    _, variant_path, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "safe.pdf"
    _write_pdf(source_pdf, ["ISBN-10 0123456789\nISBN-13 9780123456786"])

    validate_public_pdf(
        source_pdf,
        variant=load_variant(variant_path),
        publish=load_publish_config(publish_path),
        sot_path=sot_path,
    )


def test_validate_public_pdf_rejects_unlabeled_compact_third_party_phone(
    tmp_path: Path,
) -> None:
    _, variant_path, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "unsafe.pdf"
    _write_pdf(source_pdf, ["Advisor 2125550199"])

    with pytest.raises(PublicPdfError, match="forbidden phone number"):
        validate_public_pdf(
            source_pdf,
            variant=load_variant(variant_path),
            publish=load_publish_config(publish_path),
            sot_path=sot_path,
        )


def test_validate_public_pdf_rejects_invalid_isbn_labeled_compact_phone(
    tmp_path: Path,
) -> None:
    _, variant_path, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "unsafe.pdf"
    _write_pdf(source_pdf, ["ISBN-10 2125550198"])

    with pytest.raises(PublicPdfError, match="forbidden phone number"):
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
        public_text = "\n".join(page.get_text() for page in document)
        assert "5558675309" not in public_text
        assert "|" not in public_text


@pytest.mark.parametrize("candidate", ["212.555.0199", "2125550199"])
def test_prepare_public_pdf_redacts_third_party_phone(
    tmp_path: Path,
    candidate: str,
) -> None:
    config_path, _, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "authored.pdf"
    authored_source = tmp_path / "authored.docx"
    _write_docx(authored_source, f"Example Person Advisor {candidate} Education")
    _write_pdf(source_pdf, [f"Example Person\nAdvisor | {candidate}\nEducation"])

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
        assert candidate not in public_text
        assert "|" not in public_text


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


def test_validate_public_pdf_rejects_unapproved_https_target(tmp_path: Path) -> None:
    _, variant_path, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "unapproved-link.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Profile")
    page.insert_link(
        {
            "kind": pymupdf.LINK_URI,
            "from": page.search_for("Profile")[0],
            "uri": "https://example.com/?email=advisor@example.org",
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


def test_validate_public_pdf_rejects_oversized_link_overlay(tmp_path: Path) -> None:
    _, variant_path, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "oversized-link.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Profile")
    page.insert_link(
        {
            "kind": pymupdf.LINK_URI,
            "from": page.rect,
            "uri": "https://example.com/profile",
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


def test_validate_public_pdf_rejects_raster_content(tmp_path: Path) -> None:
    _, variant_path, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "raster.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Example Person")
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), False)
    pixmap.clear_with(0)
    page.insert_image(pymupdf.Rect(72, 90, 82, 100), pixmap=pixmap)
    document.save(source_pdf)
    document.close()

    with pytest.raises(PublicPdfError, match="unverifiable raster content"):
        validate_public_pdf(
            source_pdf,
            variant=load_variant(variant_path),
            publish=load_publish_config(publish_path),
            sot_path=sot_path,
        )


def test_validate_public_pdf_rejects_complex_vector_content(tmp_path: Path) -> None:
    _, variant_path, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "vector.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Example Person")
    page.draw_circle((100, 100), 10, color=(0, 0, 0))
    document.save(source_pdf)
    document.close()

    with pytest.raises(PublicPdfError, match="unverifiable vector content"):
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


def test_prepare_public_pdf_rejects_unapproved_rectangle_layout(tmp_path: Path) -> None:
    config_path, _, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "unapproved-layout.pdf"
    authored_source = tmp_path / "authored.docx"
    _write_docx(authored_source, "Example Person Education")
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Example Person\nEducation")
    page.draw_rect(pymupdf.Rect(72, 90, 110, 91), fill=(0, 0, 0))
    document.save(source_pdf)
    document.close()

    with pytest.raises(PublicPdfError, match="visual fingerprint is not approved"):
        prepare_public_pdf(
            authored_source=authored_source,
            source_pdf=source_pdf,
            config_path=config_path,
            variant_id="base",
            publish_config_path=publish_path,
            sot_path=sot_path,
        )


def test_prepare_public_pdf_preserves_approved_graphics_during_redaction(
    tmp_path: Path,
) -> None:
    config_path, _, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "authored.pdf"
    authored_source = tmp_path / "authored.docx"
    _write_docx(authored_source, "Example Person 555.867.5309 Education")
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Example Person | 555.867.5309\nEducation", fontsize=11)
    page.draw_rect(page.search_for("555.867.5309")[0], color=(0, 0, 0))
    document.save(source_pdf)
    document.close()

    with pymupdf.open(source_pdf) as source:
        source_fingerprint = _visual_fingerprint(source)
    publish_path.write_text(
        publish_path.read_text().replace(
            "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
            source_fingerprint,
        )
    )

    result = prepare_public_pdf(
        authored_source=authored_source,
        source_pdf=source_pdf,
        config_path=config_path,
        variant_id="base",
        publish_config_path=publish_path,
        sot_path=sot_path,
    )

    with pymupdf.open(result.output_pdf) as public:
        assert _visual_fingerprint(public) == source_fingerprint


def test_visual_fingerprint_includes_vector_line_styles() -> None:
    def fingerprint(*, line_cap: int, line_join: int) -> str:
        document = pymupdf.open()
        page = document.new_page()
        page.draw_rect(
            pymupdf.Rect(72, 72, 120, 100),
            color=(0, 0, 0),
            width=4,
            lineCap=line_cap,
            lineJoin=line_join,
        )
        result = _visual_fingerprint(document)
        document.close()
        return result

    baseline = fingerprint(line_cap=0, line_join=0)
    assert fingerprint(line_cap=0, line_join=1) != baseline
    assert fingerprint(line_cap=1, line_join=0) != baseline


def test_prepare_public_pdf_restores_pdf_and_manifest_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path, _, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "authored.pdf"
    authored_source = tmp_path / "authored.docx"
    _write_docx(authored_source, "Example Person Education")
    _write_pdf(source_pdf, ["Example Person\nEducation"])
    output_pdf = tmp_path / "var/publish/base/cv.pdf"
    manifest_path = output_pdf.parent / "manifest.json"
    output_pdf.parent.mkdir(parents=True)
    output_pdf.write_bytes(b"old pdf")
    manifest_path.write_text("old manifest\n")
    replace = atomic.os.replace
    staged_replacements = 0

    def fail_second_staged_replace(source: Path | str, destination: Path | str) -> None:
        nonlocal staged_replacements
        if ".cvw-stage-" in Path(source).name:
            staged_replacements += 1
            if staged_replacements == 2:
                raise OSError("simulated replacement failure")
        replace(source, destination)

    monkeypatch.setattr(atomic.os, "replace", fail_second_staged_replace)

    with pytest.raises(PublicPdfError, match="prior artifacts were restored"):
        prepare_public_pdf(
            authored_source=authored_source,
            source_pdf=source_pdf,
            config_path=config_path,
            variant_id="base",
            publish_config_path=publish_path,
            sot_path=sot_path,
        )

    assert output_pdf.read_bytes() == b"old pdf"
    assert manifest_path.read_text() == "old manifest\n"
    assert not list(output_pdf.parent.glob("*.cvw-stage-*"))
    assert not list(output_pdf.parent.glob("*.cvw-backup-*"))


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


def test_publish_config_requires_valid_visual_fingerprint(tmp_path: Path) -> None:
    _, _, publish_path, _ = _write_workspace(tmp_path)
    publish_path.write_text(
        publish_path.read_text().replace(
            "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
            "not-a-hash",
        )
    )

    with pytest.raises(PublishError, match="lowercase SHA-256 visual fingerprint"):
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
    page.add_redact_annot(page.search_for("Person")[0], fill=None, cross_out=False)
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


def test_prepare_public_pdf_rejects_nonterminal_forbidden_section(
    tmp_path: Path,
) -> None:
    config_path, _, publish_path, sot_path = _write_workspace(tmp_path)
    source_pdf = tmp_path / "authored.pdf"
    authored_source = tmp_path / "authored.docx"
    text = "Example Person References Advisor Education Public research"
    _write_docx(authored_source, text)
    _write_pdf(
        source_pdf,
        ["Example Person\nReferences\nAdvisor\nEducation\nPublic research"],
    )

    with pytest.raises(PublicPdfError, match="must be terminal"):
        prepare_public_pdf(
            authored_source=authored_source,
            source_pdf=source_pdf,
            config_path=config_path,
            variant_id="base",
            publish_config_path=publish_path,
            sot_path=sot_path,
        )


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
