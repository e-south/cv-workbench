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
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree

import pymupdf
import yaml

from cvworkbench.build.paths import output_path
from cvworkbench.config import resolve_publish_path, resolve_variant_path
from cvworkbench.ops.publish import PublishConfig, load_publish_config
from cvworkbench.variants import Variant, load_variant

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_CANDIDATE_PATTERN = re.compile(r"(?<!\w)\+?\d(?:[\d\s().\-\u2010-\u2015]*\d)?(?!\w)")
MIN_SOURCE_TOKEN_COVERAGE = 0.9


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


@dataclass(frozen=True)
class _SourceMatch:
    pdf_token_coverage: float
    docx_token_coverage: float


@dataclass(frozen=True)
class _RedactionRegion:
    page_index: int
    rect: tuple[float, float, float, float]


@dataclass(frozen=True)
class _RedactionPlan:
    count: int
    regions: tuple[_RedactionRegion, ...]


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
    person = _load_person(sot_path)

    document = _open_pdf(source_pdf)
    try:
        redaction_plan = _mark_private_content(document, publish, person)
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
            validate_public_pdf_layout(
                source_pdf,
                temporary_pdf,
                allowed_redactions=redaction_plan.regions,
            )
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
        redaction_count=redaction_plan.count,
        source_match=source_match,
    )
    return PublicPdfResult(
        output_pdf=output_pdf,
        manifest_path=manifest_path,
        redaction_count=redaction_plan.count,
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
        _validate_verifiable_visual_content(document)
        _validate_pdf_links(document)
        text = "\n".join(page.get_text() for page in document)
    finally:
        document.close()

    person = _load_person(sot_path)
    forbidden_phone_digits = _forbidden_phone_digits(person, publish)
    if any(
        _matches_forbidden_phone(match.group(0), forbidden_phone_digits)
        for match in PHONE_CANDIDATE_PATTERN.finditer(text)
    ):
        raise PublicPdfError("Public PDF contains a forbidden phone number")

    observed_emails = {match.casefold() for match in EMAIL_PATTERN.findall(text)}
    allowed_emails: set[str] = set()
    if observed_emails:
        if "email" in variant.contact_fields and "email" not in publish.forbidden_contact_fields:
            email = person.get("email")
            if isinstance(email, str) and email.strip():
                allowed_emails.add(email.strip().casefold())
    unauthorized_emails = sorted(observed_emails - allowed_emails)
    if unauthorized_emails:
        raise PublicPdfError("Public PDF contains an unauthorized email address")

    normalized_lines = {line.strip().casefold() for line in text.splitlines()}
    for section in publish.forbidden_sections:
        marker = _section_label(section).casefold()
        if marker in normalized_lines:
            raise PublicPdfError(f"Public PDF contains forbidden section heading: {section}")


def validate_public_pdf_layout(
    source_path: Path,
    public_path: Path,
    *,
    allowed_redactions: tuple[_RedactionRegion, ...] = (),
) -> None:
    """Prove that sanitization did not reflow or restyle surviving text."""

    source = _open_pdf(source_path)
    public = _open_pdf(public_path)
    try:
        if source.page_count != public.page_count:
            raise PublicPdfError("Public PDF layout drift: page count changed")

        allowed_by_page: dict[int, list[pymupdf.Rect]] = {}
        for region in allowed_redactions:
            if region.page_index < 0 or region.page_index >= source.page_count:
                raise PublicPdfError(
                    "Public PDF layout contract contains an invalid redaction page"
                )
            allowed_by_page.setdefault(region.page_index, []).append(pymupdf.Rect(region.rect))

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
            public_cursor = 0
            while source_cursor < len(source_characters):
                source_character = source_characters[source_cursor]
                if public_cursor < len(public_characters) and _characters_match(
                    source_character,
                    public_characters[public_cursor],
                ):
                    source_cursor += 1
                    public_cursor += 1
                    continue
                if _character_is_within_redaction(
                    source_character,
                    allowed_by_page.get(page_index, []),
                ):
                    source_cursor += 1
                    continue
                value = repr(source_character.value)
                raise PublicPdfError(
                    "Public PDF layout drift on page "
                    f"{page_index + 1}: unapproved removal near character {value}"
                )
            if public_cursor != len(public_characters):
                value = repr(public_characters[public_cursor].value)
                raise PublicPdfError(
                    "Public PDF layout drift on page "
                    f"{page_index + 1}: unexpected character near {value}"
                )
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


def _character_is_within_redaction(
    character: _PdfCharacter,
    regions: list[pymupdf.Rect],
) -> bool:
    character_rect = pymupdf.Rect(character.bbox)
    return any(character_rect.intersects(region) for region in regions)


def _validate_pdf_links(document: pymupdf.Document) -> None:
    for page_index, page in enumerate(document):
        word_rectangles = [pymupdf.Rect(*word[:4]) for word in page.get_text("words")]
        for link in page.get_links():
            uri = link.get("uri")
            parsed = urlsplit(uri) if isinstance(uri, str) else None
            link_rect = pymupdf.Rect(link["from"])
            covers_visible_text = any(link_rect.intersects(rect) for rect in word_rectangles)
            if (
                link.get("kind") != pymupdf.LINK_URI
                or parsed is None
                or parsed.scheme.casefold() != "https"
                or not parsed.hostname
                or not covers_visible_text
            ):
                raise PublicPdfError(
                    f"Public PDF contains an unsafe or hidden link on page {page_index + 1}"
                )


def _validate_verifiable_visual_content(document: pymupdf.Document) -> None:
    for page_index, page in enumerate(document):
        if page.get_images(full=True):
            raise PublicPdfError(
                f"Public PDF contains unverifiable raster content on page {page_index + 1}"
            )
        if any(True for _ in page.annots()):
            raise PublicPdfError(
                f"Public PDF contains unsupported annotations on page {page_index + 1}"
            )
        if any(True for _ in page.widgets()):
            raise PublicPdfError(
                f"Public PDF contains unsupported form widgets on page {page_index + 1}"
            )
        for drawing in page.get_drawings():
            if any(item[0] != "re" for item in drawing.get("items", [])):
                raise PublicPdfError(
                    f"Public PDF contains unverifiable vector content on page {page_index + 1}"
                )


def _mark_private_content(
    document: pymupdf.Document,
    publish: PublishConfig,
    person: dict[str, Any],
) -> _RedactionPlan:
    regions: list[_RedactionRegion] = []
    forbidden_phone_digits = _forbidden_phone_digits(person, publish)
    if forbidden_phone_digits:
        for page_index, page in enumerate(document):
            page_text = page.get_text()
            for match in PHONE_CANDIDATE_PATTERN.finditer(page_text):
                if not _matches_forbidden_phone(match.group(0), forbidden_phone_digits):
                    continue
                for rect in page.search_for(match.group(0)):
                    region = _RedactionRegion(page_index=page_index, rect=tuple(rect))
                    if region in regions:
                        continue
                    page.add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)
                    regions.append(region)

    for section in publish.forbidden_sections:
        regions.extend(_mark_section_and_following_pages(document, section))
    return _RedactionPlan(count=len(regions), regions=tuple(regions))


def _forbidden_phone_digits(
    person: dict[str, Any],
    publish: PublishConfig,
) -> tuple[str, ...]:
    if "phone" not in publish.forbidden_contact_fields:
        return ()

    raw = person.get("phone")
    values = raw if isinstance(raw, list) else [raw]
    digits = tuple(
        normalized
        for value in values
        if isinstance(value, str)
        if (normalized := re.sub(r"\D", "", value))
    )
    if not digits:
        raise PublicPdfError("Phone publication policy requires phone data in the Source of Truth")
    return digits


def _matches_forbidden_phone(candidate: str, forbidden_digits: tuple[str, ...]) -> bool:
    candidate_digits = re.sub(r"\D", "", candidate)
    for expected in forbidden_digits:
        if candidate_digits == expected:
            return True
        if len(expected) == 11 and expected.startswith("1") and candidate_digits == expected[1:]:
            return True
        if len(candidate_digits) == 11 and candidate_digits.startswith("1"):
            if candidate_digits[1:] == expected:
                return True
    return False


def _mark_section_and_following_pages(
    document: pymupdf.Document,
    section: str,
) -> list[_RedactionRegion]:
    label = _section_label(section)
    heading_page: int | None = None
    heading_rect: pymupdf.Rect | None = None
    marker_exists = False

    for page_index, page in enumerate(document):
        page_text = page.get_text()
        marker_exists = marker_exists or bool(
            re.search(rf"\b{re.escape(label)}\b", page_text, re.IGNORECASE)
        )
        exact_heading_rect = _exact_line_rect(page, label)
        if exact_heading_rect is None:
            continue
        heading_page = page_index
        heading_rect = exact_heading_rect
        break

    if heading_page is None or heading_rect is None:
        if marker_exists:
            raise PublicPdfError(f"Could not isolate forbidden section heading: {section}")
        return []

    regions: list[_RedactionRegion] = []
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
        regions.append(_RedactionRegion(page_index=page_index, rect=tuple(rect)))
    return regions


def _exact_line_rect(page: pymupdf.Page, label: str) -> pymupdf.Rect | None:
    payload = page.get_text("dict", sort=True)
    for block in payload.get("blocks", []):
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if text.casefold() == label.casefold():
                return pymupdf.Rect(line["bbox"])
    return None


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


def _validate_authored_source(authored_source: Path, source_pdf: Path) -> _SourceMatch:
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

    authored_tokens = Counter(_normalized_tokens(authored_text))
    source_tokens = Counter(_normalized_tokens(source_text))
    if not authored_tokens or not source_tokens:
        raise PublicPdfError("Authored DOCX and exported PDF must both contain extractable text")
    overlap = sum((authored_tokens & source_tokens).values())
    pdf_coverage = overlap / source_tokens.total()
    docx_coverage = overlap / authored_tokens.total()
    if pdf_coverage < MIN_SOURCE_TOKEN_COVERAGE or docx_coverage < MIN_SOURCE_TOKEN_COVERAGE:
        raise PublicPdfError("Exported PDF does not correspond closely enough to the authored DOCX")
    return _SourceMatch(
        pdf_token_coverage=pdf_coverage,
        docx_token_coverage=docx_coverage,
    )


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
    source_match: _SourceMatch,
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
            "pdf_token_coverage": round(source_match.pdf_token_coverage, 6),
            "docx_token_coverage": round(source_match.docx_token_coverage, 6),
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
