"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/public_pdf.py

Prepares faithful authored PDFs for public distribution.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pymupdf
import yaml

from cvworkbench.build.paths import output_path
from cvworkbench.config import resolve_publish_path, resolve_variant_path
from cvworkbench.ops.publish import PublishConfig, load_publish_config
from cvworkbench.variants import Variant, load_variant

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\w)")


class PublicPdfError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublicPdfResult:
    output_pdf: Path
    manifest_path: Path
    redaction_count: int


@dataclass(frozen=True)
class _PdfCharacter:
    value: str
    origin: tuple[float, float]
    bbox: tuple[float, float, float, float]
    font: str
    size: float
    flags: int
    color: int


def prepare_public_pdf(
    *,
    authored_source: Path,
    source_pdf: Path,
    config_path: Path,
    variant_id: str,
    publish_config_path: Path,
    sot_path: Path,
) -> PublicPdfResult:
    """Sanitize an authored PDF without re-typesetting its public content."""

    if not source_pdf.exists():
        raise PublicPdfError(f"Authored PDF not found: {source_pdf}")
    source_match = _validate_authored_source(authored_source, source_pdf)
    variant = load_variant(resolve_variant_path(variant_id, config_path))
    publish = load_publish_config(publish_config_path)
    _validate_publish_variant(variant, publish)
    if "pdf" not in variant.outputs:
        raise PublicPdfError(f"Publish variant '{variant.id}' does not declare a PDF output")

    output_pdf = output_path(resolve_publish_path(config_path) / variant.id, variant, "pdf")
    if source_pdf.resolve() == output_pdf.resolve():
        raise PublicPdfError("Authored source and public output must be different files")
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    document = _open_pdf(source_pdf)
    try:
        redaction_count = _mark_private_content(document, publish)
        for page in document:
            page.apply_redactions(images=0, graphics=0, text=0)
        document.scrub(remove_links=False)
        document.set_metadata({})

        temporary_pdf = _temporary_pdf_path(output_pdf)
        try:
            document.save(
                temporary_pdf,
                garbage=4,
                clean=True,
                deflate=True,
                use_objstms=1,
                reproducible=True,
                no_new_id=True,
            )
            validate_public_pdf(
                temporary_pdf,
                variant=variant,
                publish=publish,
                sot_path=sot_path,
            )
            validate_public_pdf_layout(source_pdf, temporary_pdf)
            os.replace(temporary_pdf, output_pdf)
        finally:
            temporary_pdf.unlink(missing_ok=True)
    finally:
        document.close()

    manifest_path = output_pdf.parent / "manifest.json"
    _write_publication_manifest(
        manifest_path,
        authored_source=authored_source,
        source_pdf=source_pdf,
        output_pdf=output_pdf,
        variant=variant,
        publish=publish,
        redaction_count=redaction_count,
        source_match=source_match,
    )
    return PublicPdfResult(
        output_pdf=output_pdf,
        manifest_path=manifest_path,
        redaction_count=redaction_count,
    )


def validate_public_pdf(
    path: Path,
    *,
    variant: Variant,
    publish: PublishConfig,
    sot_path: Path,
) -> None:
    """Fail closed when a PDF exposes contact or section data forbidden by policy."""

    document = _open_pdf(path)
    try:
        if document.needs_pass:
            raise PublicPdfError(f"Public PDF must not be encrypted: {path}")
        if document.embfile_count():
            raise PublicPdfError(f"Public PDF must not contain embedded files: {path}")
        text = "\n".join(page.get_text() for page in document)
    finally:
        document.close()

    if "phone" in publish.forbidden_contact_fields and PHONE_PATTERN.search(text):
        raise PublicPdfError("Public PDF contains a forbidden phone number")

    observed_emails = {match.casefold() for match in EMAIL_PATTERN.findall(text)}
    allowed_emails: set[str] = set()
    if observed_emails:
        person = _load_person(sot_path)
        if "email" in variant.contact_fields and "email" not in publish.forbidden_contact_fields:
            email = person.get("email")
            if isinstance(email, str) and email.strip():
                allowed_emails.add(email.strip().casefold())
    unauthorized_emails = sorted(observed_emails - allowed_emails)
    if unauthorized_emails:
        raise PublicPdfError("Public PDF contains an unauthorized email address")

    normalized_text = text.casefold()
    for section in publish.forbidden_sections:
        marker = _section_label(section).casefold()
        if re.search(rf"\b{re.escape(marker)}\b", normalized_text):
            raise PublicPdfError(f"Public PDF contains forbidden section heading: {section}")


def validate_public_pdf_layout(source_path: Path, public_path: Path) -> None:
    """Prove that sanitization did not reflow or restyle surviving text."""

    source = _open_pdf(source_path)
    public = _open_pdf(public_path)
    try:
        if source.page_count != public.page_count:
            raise PublicPdfError("Public PDF layout drift: page count changed")

        for page_index in range(source.page_count):
            source_page = source[page_index]
            public_page = public[page_index]
            if source_page.rotation != public_page.rotation:
                raise PublicPdfError(
                    f"Public PDF layout drift on page {page_index + 1}: rotation changed"
                )
            for label, source_rect, public_rect in (
                ("page", source_page.rect, public_page.rect),
                ("media box", source_page.mediabox, public_page.mediabox),
                ("crop box", source_page.cropbox, public_page.cropbox),
            ):
                if not _coordinates_match(tuple(source_rect), tuple(public_rect)):
                    raise PublicPdfError(
                        f"Public PDF layout drift on page {page_index + 1}: {label} changed"
                    )

            source_characters = _pdf_characters(source_page)
            public_characters = _pdf_characters(public_page)
            source_cursor = 0
            for public_character in public_characters:
                while source_cursor < len(source_characters) and not _characters_match(
                    source_characters[source_cursor], public_character
                ):
                    source_cursor += 1
                if source_cursor == len(source_characters):
                    value = repr(public_character.value)
                    raise PublicPdfError(
                        "Public PDF layout drift on page "
                        f"{page_index + 1} near character {value}"
                    )
                source_cursor += 1
    finally:
        public.close()
        source.close()


def _pdf_characters(page: pymupdf.Page) -> list[_PdfCharacter]:
    characters: list[_PdfCharacter] = []
    payload = page.get_text("rawdict", sort=True)
    for block in payload.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                for character in span.get("chars", []):
                    characters.append(
                        _PdfCharacter(
                            value=character["c"],
                            origin=tuple(character["origin"]),
                            bbox=tuple(character["bbox"]),
                            font=span["font"],
                            size=span["size"],
                            flags=span["flags"],
                            color=span["color"],
                        )
                    )
    return characters


def _characters_match(source: _PdfCharacter, public: _PdfCharacter) -> bool:
    return (
        source.value == public.value
        and _coordinates_match(source.origin, public.origin)
        and _coordinates_match(source.bbox, public.bbox)
        and source.font == public.font
        and abs(source.size - public.size) <= 0.001
        and source.flags == public.flags
        and source.color == public.color
    )


def _coordinates_match(source: tuple[float, ...], public: tuple[float, ...]) -> bool:
    return len(source) == len(public) and all(
        abs(source_value - public_value) <= 0.02
        for source_value, public_value in zip(source, public, strict=True)
    )


def _mark_private_content(document: pymupdf.Document, publish: PublishConfig) -> int:
    redaction_count = 0
    if "phone" in publish.forbidden_contact_fields:
        for page in document:
            page_text = page.get_text()
            for match in PHONE_PATTERN.finditer(page_text):
                for rect in page.search_for(match.group(0)):
                    page.add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)
                    redaction_count += 1

    for section in publish.forbidden_sections:
        redaction_count += _mark_section_and_following_pages(document, section)
    return redaction_count


def _mark_section_and_following_pages(document: pymupdf.Document, section: str) -> int:
    label = _section_label(section)
    heading_page: int | None = None
    heading_rect: pymupdf.Rect | None = None
    marker_exists = False

    for page_index, page in enumerate(document):
        page_text = page.get_text()
        marker_exists = marker_exists or bool(
            re.search(rf"\b{re.escape(label)}\b", page_text, re.IGNORECASE)
        )
        lines = [line.strip() for line in page_text.splitlines()]
        if not any(line.casefold() == label.casefold() for line in lines):
            continue
        rectangles = page.search_for(label)
        if not rectangles:
            raise PublicPdfError(f"Could not locate forbidden section heading: {section}")
        heading_page = page_index
        heading_rect = rectangles[0]
        break

    if heading_page is None or heading_rect is None:
        if marker_exists:
            raise PublicPdfError(f"Could not isolate forbidden section heading: {section}")
        return 0

    count = 0
    for page_index in range(heading_page, document.page_count):
        page = document[page_index]
        if page_index == heading_page:
            rect = pymupdf.Rect(
                page.rect.x0,
                max(page.rect.y0, heading_rect.y0 - 1),
                page.rect.x1,
                page.rect.y1,
            )
        else:
            rect = page.rect
        page.add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)
        count += 1
    return count


def _validate_publish_variant(variant: Variant, publish: PublishConfig) -> None:
    if variant.id not in publish.variants:
        raise PublicPdfError(f"Variant '{variant.id}' is not allowed by publish policy")
    missing_tags = sorted(set(publish.required_exclude_tags) - set(variant.exclude_tags))
    if missing_tags:
        raise PublicPdfError(
            f"Publish variant is missing required exclude tags: {', '.join(missing_tags)}"
        )
    forbidden_contacts = sorted(set(variant.contact_fields) & set(publish.forbidden_contact_fields))
    if forbidden_contacts:
        raise PublicPdfError(
            "Publish variant includes forbidden contact fields: " + ", ".join(forbidden_contacts)
        )
    forbidden_sections = sorted(set(variant.order) & set(publish.forbidden_sections))
    if forbidden_sections:
        raise PublicPdfError(
            f"Publish variant includes forbidden sections: {', '.join(forbidden_sections)}"
        )


def _open_pdf(path: Path) -> pymupdf.Document:
    try:
        document = pymupdf.open(path)
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise PublicPdfError(f"Invalid PDF artifact: {path}") from exc
    if not document.is_pdf:
        document.close()
        raise PublicPdfError(f"Public artifact is not a PDF: {path}")
    return document


def _load_person(sot_path: Path) -> dict[str, Any]:
    person_path = sot_path / "person.yaml"
    if not person_path.exists():
        raise PublicPdfError(f"Person Source of Truth not found: {person_path}")
    raw = yaml.safe_load(person_path.read_text())
    if not isinstance(raw, dict):
        raise PublicPdfError(f"Invalid person Source of Truth: {person_path}")
    return raw


def _section_label(section: str) -> str:
    return section.replace("_", " ").replace("-", " ").strip().title()


def _validate_authored_source(authored_source: Path, source_pdf: Path) -> float:
    if not authored_source.exists():
        raise PublicPdfError(f"Authored source not found: {authored_source}")
    if authored_source.suffix.casefold() != ".docx":
        raise PublicPdfError("Authored source must be a DOCX file")
    try:
        with zipfile.ZipFile(authored_source) as archive:
            names = set(archive.namelist())
            if "word/document.xml" not in names:
                raise PublicPdfError(f"Invalid authored DOCX: {authored_source}")
            if "word/vbaProject.bin" in names:
                raise PublicPdfError("Authored DOCX must not contain macros")
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, ElementTree.ParseError, KeyError) as exc:
        raise PublicPdfError(f"Invalid authored DOCX: {authored_source}") from exc

    authored_text = " ".join(
        element.text or "" for element in root.iter() if element.tag.endswith("}t")
    )
    source_document = _open_pdf(source_pdf)
    try:
        source_text = " ".join(page.get_text() for page in source_document)
    finally:
        source_document.close()

    authored_tokens = set(_normalized_tokens(authored_text))
    source_tokens = set(_normalized_tokens(source_text))
    if not authored_tokens or not source_tokens:
        raise PublicPdfError("Authored DOCX and exported PDF must both contain extractable text")
    coverage = len(authored_tokens & source_tokens) / len(source_tokens)
    if coverage < 0.9:
        raise PublicPdfError("Exported PDF does not correspond closely enough to the authored DOCX")
    return coverage


def _normalized_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def _temporary_pdf_path(output_pdf: Path) -> Path:
    descriptor, value = tempfile.mkstemp(
        prefix=f".{output_pdf.stem}.",
        suffix=output_pdf.suffix,
        dir=output_pdf.parent,
    )
    os.close(descriptor)
    return Path(value)


def _write_publication_manifest(
    path: Path,
    *,
    authored_source: Path,
    source_pdf: Path,
    output_pdf: Path,
    variant: Variant,
    publish: PublishConfig,
    redaction_count: int,
    source_match: float,
) -> None:
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
        "outputs": {"pdf": output_pdf.name},
        "output_hashes": {"pdf": _hash_file(output_pdf)},
        "source": {
            "authored_name": authored_source.name,
            "authored_sha256": _hash_file(authored_source),
            "exported_pdf_name": source_pdf.name,
            "exported_pdf_sha256": _hash_file(source_pdf),
            "text_token_coverage": round(source_match, 6),
        },
        "transformation": {
            "kind": "semantic-redaction",
            "forbidden_contact_fields": list(publish.forbidden_contact_fields),
            "forbidden_sections": list(publish.forbidden_sections),
            "redaction_count": redaction_count,
        },
    }
    temporary_manifest = path.with_name(f".{path.name}.tmp")
    temporary_manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary_manifest, path)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()
