"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/publication/test_state.py

Tests authored publication freshness and review declarations against actual files.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

import pytest

from cvworkbench.ops.publication.pdf import prepare_public_pdf
from cvworkbench.ops.publication.state import (
    PublicationStateError,
    inspect_publication,
    record_publication_review,
)
from cvworkbench.ops.syncing import SyncError, sync_site
from tests.ops.publication.test_pdf import _write_docx, _write_pdf, _write_workspace


@pytest.mark.parametrize(
    "filename, expected",
    [("preparation.json", "invalid"), ("review-receipt.json", "review_required")],
)
@pytest.mark.parametrize("version", [True, None])
def test_record_schema_version_requires_explicit_integer(tmp_path, filename, expected, version):
    config, *_ = _prepare(tmp_path)
    state = inspect_publication(config, "base")
    record_publication_review(config, "base", state.pdf_sha256)
    path = tmp_path / "var/publish/base" / filename
    data = json.loads(path.read_text())
    if version is None:
        data.pop("schema_version")
    else:
        data["schema_version"] = version
    path.write_text(json.dumps(data))
    assert inspect_publication(config, "base").state == expected


def test_preparation_rejects_a_packet_that_identifies_another_pdf(tmp_path):
    config, *_ = _prepare(tmp_path)
    state = inspect_publication(config, "base")
    path = Path(state.preparation_path)
    data = json.loads(path.read_text())
    packet_pdf = Path(state.review_path).parent / "cv.pdf"
    _write_pdf(packet_pdf, ["A different PDF in the packet"])
    data["review_files"]["cv.pdf"] = hashlib.sha256(packet_pdf.read_bytes()).hexdigest()
    path.write_text(json.dumps(data))
    assert inspect_publication(config, "base").state == "invalid"


def test_sync_requires_current_review_before_any_site_write(tmp_path: Path) -> None:
    config, docx, *_ = _prepare(tmp_path)
    site = tmp_path / "site"
    (site / "public/cv").mkdir(parents=True)
    (site / "page.md").write_text("---\ncvPdf: /old.pdf\n---\n")
    target = site / "public/cv/cv.pdf"
    target.write_bytes(b"previous site artifact")
    site_config = config.parent / "site-sync.yaml"
    site_config.write_text(
        f"site:\n  repo_path: {site}\n  publish_variant: base\n"
        "  cv_pdf_dir: public/cv\n  cv_pdf_name: cv.pdf\n  cv_manifest: public/cv/manifest.json\n"
        "  cv_page: page.md\n  cv_page_frontmatter_key: cvPdf\n"
    )
    with pytest.raises(SyncError, match="review_required"):
        sync_site(config_path=config, site_config_path=site_config, mode="local")
    assert target.read_bytes() == b"previous site artifact"
    assert not (site / "public/cv/manifest.json").exists()
    state = inspect_publication(config, "base")
    record_publication_review(config, "base", state.pdf_sha256)
    sync_site(config_path=config, site_config_path=site_config, mode="local")
    assert hashlib.sha256(target.read_bytes()).hexdigest() == state.pdf_sha256
    assert "authored.docx" not in (site / "public/cv/manifest.json").read_text()
    assert not list(site.rglob("preparation.json"))
    assert not list(site.rglob("review-receipt.json"))
    _write_docx(docx, "A newer source awaiting export")
    with pytest.raises(SyncError, match="stale_source"):
        sync_site(config_path=config, site_config_path=site_config, mode="local")
    assert hashlib.sha256(target.read_bytes()).hexdigest() == state.pdf_sha256


def _prepare(root: Path):
    config, variant, policy, sot = _write_workspace(root)
    docx, pdf = root / "authored.docx", root / "export.pdf"
    text = "Example Person\nperson@example.com\nExperience\nResearch and engineering"
    _write_docx(docx, text)
    _write_pdf(pdf, [text])
    prepare_public_pdf(
        authored_source=docx,
        source_pdf=pdf,
        config_path=config,
        variant_id="base",
        publish_config_path=policy,
        sot_path=sot,
    )
    return config, docx, pdf, policy, sot


@pytest.mark.parametrize("mutation", ["edit", "remove"])
def test_publication_inspection_uses_captured_workbench_settings(tmp_path, monkeypatch, mutation):
    import yaml

    config, *_ = _prepare(tmp_path)
    expected = inspect_publication(config, "base")
    assert expected.state == "review_required"
    original_read = Path.read_bytes
    reads = []

    def mutate_after_read(path):
        content = original_read(path)
        if path == config:
            reads.append(path)
            if mutation == "edit":
                data = yaml.safe_load(content)
                data["paths"]["sot"] = "../different/sot"
                data["paths"]["reviews"] = "../different/reviews"
                path.write_text(yaml.safe_dump(data))
            else:
                path.unlink()
        return content

    monkeypatch.setattr(Path, "read_bytes", mutate_after_read)
    assert inspect_publication(config, "base") == expected
    assert reads == [config]


def test_publication_review_is_explicit_and_bound_to_current_bytes(tmp_path: Path) -> None:
    config, docx, _, _, _ = _prepare(tmp_path)
    state = inspect_publication(config, "base")
    assert state.state == "review_required"
    assert state.authored_source == str(docx.resolve())
    assert stat.S_IMODE(Path(state.preparation_path).stat().st_mode) == 0o600
    receipt = Path(state.receipt_path)
    with pytest.raises(PublicationStateError, match="hash"):
        record_publication_review(config, "base", "0" * 64)
    assert not receipt.exists()
    record_publication_review(config, "base", state.pdf_sha256)
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert inspect_publication(config, "base").state == "reviewed"
    _write_docx(docx, "A newly edited authored CV")
    assert inspect_publication(config, "base").state == "stale_source"


@pytest.mark.parametrize(
    "changed, expected",
    [
        ("export.pdf", "stale_export"),
        ("config/publish.yaml", "stale_configuration"),
        ("local/sot/person.yaml", "stale_configuration"),
        ("var/publish/base/cv.pdf", "invalid"),
    ],
)
def test_changed_publication_inputs_are_observable(
    tmp_path: Path, changed: str, expected: str
) -> None:
    config, *_ = _prepare(tmp_path)
    path = tmp_path / changed
    path.write_bytes(path.read_bytes() + b"\nchanged\n")
    assert inspect_publication(config, "base").state == expected


def test_missing_source_and_corrupt_review_packet_do_not_look_reviewed(tmp_path: Path) -> None:
    config, docx, *_ = _prepare(tmp_path)
    state = inspect_publication(config, "base")
    image = Path(state.review_path).parent / "page-0001.png"
    image.write_bytes(b"incorrect preview")
    assert inspect_publication(config, "base").state == "invalid"
    with pytest.raises(PublicationStateError):
        record_publication_review(config, "base", state.pdf_sha256)
    docx.unlink()
    assert inspect_publication(config, "base").state == "missing"


def test_identical_preparation_preserves_review_and_inspection_does_not_write(
    tmp_path: Path,
) -> None:
    config, docx, pdf, policy, sot = _prepare(tmp_path)
    state = inspect_publication(config, "base")
    record_publication_review(config, "base", state.pdf_sha256)
    prepare_public_pdf(
        authored_source=docx,
        source_pdf=pdf,
        config_path=config,
        variant_id="base",
        publish_config_path=policy,
        sot_path=sot,
    )
    assert inspect_publication(config, "base").state == "reviewed"
    before = {
        p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob("*") if p.is_file()
    }
    inspect_publication(config, "base")
    after = {
        p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob("*") if p.is_file()
    }
    assert before == after
