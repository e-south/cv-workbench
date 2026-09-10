"""Publication disclosure includes PDF object strings beyond visible page text."""

from pathlib import Path

import pymupdf
import pytest

from cvworkbench.ops.publication.pdf import (
    PublicPdfError,
    prepare_public_pdf,
    validate_public_pdf,
    validate_public_pdf_content,
)
from cvworkbench.ops.publication.policy import load_publish_config
from cvworkbench.variants import load_variant

from .test_pdf import _write_docx, _write_pdf, _write_workspace


def _add_object_text(path: Path, surface: str, text: str) -> None:
    with pymupdf.open(path) as document:
        if surface == "outline":
            document.set_toc([[1, text, 1]])
        else:
            root = document.get_new_xref()
            element = document.get_new_xref()
            encoded = pymupdf.get_pdf_str(text)
            if surface == "indirect":
                value = document.get_new_xref()
                document.update_object(value, encoded)
                encoded = f"{value} 0 R"
            fields = f"/Alt {encoded}"
            if surface == "nested":
                fields = f"/A [<</ActualText {encoded}>>]"
            document.update_object(root, f"<</Type/StructTreeRoot/K[{element} 0 R]>>")
            document.update_object(
                element,
                f"<</Type/StructElem/S/P/P {root} 0 R/Pg {document[0].xref} 0 R {fields}>>",
            )
            document.xref_set_key(document.pdf_catalog(), "StructTreeRoot", f"{root} 0 R")
            document.xref_set_key(document.pdf_catalog(), "MarkInfo", "<</Marked true>>")
        content = document.tobytes()
    path.write_bytes(content)


@pytest.mark.parametrize(
    ("surface", "text", "reason"),
    [
        ("outline", "Private contact: 555.867.5309", "forbidden phone number"),
        ("structure", "Private contact: 555.867.5309", "forbidden phone number"),
        ("nested", "Advisor advisor@example.org", "unauthorized email address"),
        ("indirect", "Advisor advisor@example.org", "unauthorized email address"),
        ("structure", "Référence: advisor@example.org", "unauthorized email address"),
        ("outline", "References", "forbidden section heading"),
    ],
)
@pytest.mark.parametrize("captured", [False, True])
def test_publication_rejects_private_object_text(tmp_path, surface, text, reason, captured):
    _, variant_path, policy, sot = _write_workspace(tmp_path)
    path = tmp_path / "public.pdf"
    _write_pdf(path, ["Example Person person@example.com\nEducation\nResearch"])
    _add_object_text(path, surface, text)
    with pymupdf.open(path) as document:
        assert text not in "\n".join(page.get_text() for page in document)
    options = {
        "variant": load_variant(variant_path),
        "publish": load_publish_config(policy),
        "sot_path": sot,
    }
    with pytest.raises(PublicPdfError, match=reason):
        if captured:
            validate_public_pdf_content(path.read_bytes(), **options)
        else:
            validate_public_pdf(path, **options)


@pytest.mark.parametrize("surface", ["outline", "structure", "nested", "indirect"])
def test_preparation_preserves_outputs_when_object_text_is_private(tmp_path, surface):
    config, _, policy, sot = _write_workspace(tmp_path)
    source = tmp_path / "source.pdf"
    authored = tmp_path / "authored.docx"
    text = "Example Person person@example.com\nEducation\nResearch"
    _write_docx(authored, text)
    _write_pdf(source, [text])
    options = dict(
        authored_source=authored,
        source_pdf=source,
        config_path=config,
        variant_id="base",
        publish_config_path=policy,
        sot_path=sot,
    )
    prepared = prepare_public_pdf(**options)
    before = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in (tmp_path / "var").rglob("*")
        if p.is_file()
    }
    _add_object_text(source, surface, "Private contact: 555.867.5309")
    with pytest.raises(PublicPdfError, match="forbidden phone number"):
        prepare_public_pdf(**options)
    assert {
        p.relative_to(tmp_path): p.read_bytes()
        for p in (tmp_path / "var").rglob("*")
        if p.is_file()
    } == before
    assert prepared.output_pdf.exists()


def test_preparation_preserves_public_navigation_and_accessibility_text(tmp_path):
    config, variant_path, policy, sot = _write_workspace(tmp_path)
    source = tmp_path / "source.pdf"
    authored = tmp_path / "authored.docx"
    text = "Example Person person@example.com\nEducation\nResearch"
    _write_docx(authored, text)
    _write_pdf(source, [text])
    _add_object_text(source, "structure", "Education")
    _add_object_text(source, "outline", "Education")
    prepared = prepare_public_pdf(
        authored_source=authored,
        source_pdf=source,
        config_path=config,
        variant_id="base",
        publish_config_path=policy,
        sot_path=sot,
    )
    with pymupdf.open(prepared.output_pdf) as document:
        assert document.get_toc() == [[1, "Education", 1]]
        assert document.xref_get_key(document.pdf_catalog(), "StructTreeRoot")[0] == "xref"
        assert any(
            document.xref_get_key(xref, "Alt") == ("string", "Education")
            for xref in range(1, document.xref_length())
        )
    validate_public_pdf_content(
        prepared.output_pdf.read_bytes(),
        variant=load_variant(variant_path),
        publish=load_publish_config(policy),
        sot_path=sot,
    )


@pytest.mark.parametrize("captured", [False, True])
def test_publication_rejects_external_bookmark_actions(tmp_path, captured):
    _, variant_path, policy, sot = _write_workspace(tmp_path)
    path = tmp_path / "public.pdf"
    _write_pdf(path, ["Example Person person@example.com\nEducation\nResearch"])
    with pymupdf.open(path) as document:
        document.set_toc(
            [
                [
                    1,
                    "Education",
                    -1,
                    {"kind": pymupdf.LINK_URI, "uri": "https://example.org/unapproved"},
                ]
            ]
        )
        content = document.tobytes()
    path.write_bytes(content)
    options = {
        "variant": load_variant(variant_path),
        "publish": load_publish_config(policy),
        "sot_path": sot,
    }
    with pytest.raises(PublicPdfError, match="external bookmark action"):
        if captured:
            validate_public_pdf_content(content, **options)
        else:
            validate_public_pdf(path, **options)


@pytest.mark.parametrize("action", ["javascript", "chained_uri"])
@pytest.mark.parametrize("captured", [False, True])
def test_publication_rejects_unreported_or_chained_bookmark_actions(tmp_path, action, captured):
    _, variant_path, policy, sot = _write_workspace(tmp_path)
    path = tmp_path / "public.pdf"
    _write_pdf(path, ["Example Person person@example.com\nEducation\nResearch"])
    with pymupdf.open(path) as document:
        document.set_toc([[1, "Education", 1]])
        xref = document.get_toc(simple=False)[0][3]["xref"]
        if action == "javascript":
            script = pymupdf.get_pdf_str("app.alert('example')")
            document.xref_set_key(xref, "A", f"<</S/JavaScript/JS {script}>>")
        else:
            uri = pymupdf.get_pdf_str("https://example.org/unapproved")
            document.xref_set_key(xref, "A/Next", f"<</S/URI/URI {uri}>>")
        content = document.tobytes()
    path.write_bytes(content)
    options = {
        "variant": load_variant(variant_path),
        "publish": load_publish_config(policy),
        "sot_path": sot,
    }
    with pytest.raises(PublicPdfError, match="bookmark action"):
        if captured:
            validate_public_pdf_content(content, **options)
        else:
            validate_public_pdf(path, **options)
