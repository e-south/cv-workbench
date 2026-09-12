"""Prepare native CV builds for the shared reviewed-publication boundary."""

from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf

from cvworkbench.build.paths import output_path
from cvworkbench.config import ConfigSource, read_config, resolve_publish_path, resolve_reviews_path
from cvworkbench.ops.publication.manifest import NativePublicationManifest
from cvworkbench.ops.publication.native_inputs import capture_native_build
from cvworkbench.ops.publication.packet import publication_review_files
from cvworkbench.ops.publication.pdf import (
    PublicPdfError,
    PublicPdfResult,
    _validate_public_document,
    sanitize_public_metadata,
    validate_public_pdf_layout,
)
from cvworkbench.ops.publication.reading import build_reading_html
from cvworkbench.ops.publication.record import NativePreparationRecord, json_bytes
from cvworkbench.storage import replace_files_atomically


def prepare_native_public_pdf(
    *,
    run_path: Path,
    config_path: ConfigSource,
    variant_id: str,
    publish_config_path: Path,
    sot_path: Path,
) -> PublicPdfResult:
    configuration = read_config(config_path)
    inputs = capture_native_build(
        configuration=configuration,
        run_path=run_path,
        variant_id=variant_id,
        publish_config_path=publish_config_path,
        sot_path=sot_path,
    )
    if not inputs.pdf.startswith(b"%PDF-"):
        raise PublicPdfError("Native build output is not a PDF")
    # Standard PDF timestamps are technical metadata, not contact numbers.
    # Other metadata and non-page strings still undergo disclosure inspection.
    preflight = pymupdf.open(stream=inputs.pdf, filetype="pdf")
    try:
        if not preflight.needs_pass:
            preflight.set_metadata({**preflight.metadata, "creationDate": "", "modDate": ""})
        _validate_public_document(
            preflight,
            person=inputs.person,
            variant=inputs.variant,
            publish=inputs.policy,
            label="native build",
            allowed_links=inputs.allowed_links,
        )
    finally:
        if not preflight.is_closed:
            preflight.close()
    with pymupdf.open(stream=inputs.pdf, filetype="pdf") as document:
        sanitize_public_metadata(document)
        content = document.tobytes(
            garbage=4, clean=True, deflate=True, use_objstms=1, reproducible=True, no_new_id=True
        )
    _validate_public_document(
        pymupdf.open(stream=content, filetype="pdf"),
        person=inputs.person,
        variant=inputs.variant,
        publish=inputs.policy,
        label="public native PDF",
        allowed_links=inputs.allowed_links,
    )
    with TemporaryDirectory(prefix="cvw-native-publication-") as directory:
        source, public = Path(directory) / "source.pdf", Path(directory) / "public.pdf"
        for path, data in ((source, inputs.pdf), (public, content)):
            path.touch(mode=0o600)
            path.write_bytes(data)
        validate_public_pdf_layout(source, public)
    digest = hashlib.sha256(content).hexdigest()
    output = output_path(resolve_publish_path(configuration) / variant_id, inputs.variant, "pdf")
    reading = (
        build_reading_html(
            inputs.rendered_html,
            stylesheet=inputs.html_stylesheet,
            allowed_links=inputs.allowed_links,
            person=inputs.person,
            variant=inputs.variant,
            publish=inputs.policy,
        )
        if inputs.rendered_html is not None
        else None
    )
    reading_path = output.with_suffix(".html")
    manifest = NativePublicationManifest.model_validate(
        {
            "schema_version": 1,
            "artifact_kind": "native-pdf-publication",
            "reading_html": {
                "name": reading_path.name,
                "sha256": hashlib.sha256(reading).hexdigest(),
            }
            if reading is not None
            else None,
            "variant": {
                key: getattr(inputs.variant, key)
                for key in ("id", "exclude_tags", "contact_fields", "order")
            },
            "formats": ["pdf"],
            "outputs": {"pdf": output.name},
            "output_hashes": {"pdf": digest},
            "source": {
                "run_manifest_sha256": inputs.stamps["run_manifest"].sha256,
                "rendered_markdown_sha256": inputs.stamps["rendered_markdown"].sha256,
                "exported_pdf_sha256": inputs.stamps["exported_pdf"].sha256,
                "visual_fingerprint_sha256": inputs.policy.approved_visual_fingerprint_sha256,
                "allowed_links": sorted(inputs.allowed_links),
            },
            "transformation": {
                "kind": "native-sanitization",
                "redaction_count": 0,
                "forbidden_contact_fields": inputs.policy.forbidden_contact_fields,
                "forbidden_sections": inputs.policy.forbidden_sections,
            },
        }
    )
    manifest_bytes = json_bytes(manifest.model_dump())
    packet = publication_review_files(content, reading_html=reading)
    record = NativePreparationRecord(
        schema_version=1,
        kind="native-build",
        variant=variant_id,
        **inputs.stamps,
        source_files=inputs.source_files,
        pdf_sha256=digest,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        review_files={name: hashlib.sha256(data).hexdigest() for name, data in packet.items()},
    )
    review_dir = resolve_reviews_path(configuration) / "publication" / digest
    writes = [
        (output, content),
        (output.parent / "manifest.json", manifest_bytes),
        (output.parent / "preparation.json", json_bytes(record.model_dump())),
        *((review_dir / name, data) for name, data in packet.items()),
    ]
    if reading is not None:
        writes.append((reading_path, reading))
    input_paths = {
        Path(stamp.path) for stamp in [*inputs.stamps.values(), *inputs.source_files.values()]
    }
    if any(path.resolve() in input_paths for path, _ in writes):
        raise PublicPdfError("Native publication outputs overlap captured inputs")
    inputs.verify_current()
    replace_files_atomically(writes, file_modes={path: 0o600 for path, _ in writes})
    return PublicPdfResult(output, output.parent / "manifest.json", 0, review_dir / "review.html")
