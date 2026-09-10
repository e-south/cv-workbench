"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_sync.py

Tests site sync behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
import pytest
from typer.testing import CliRunner

from cvworkbench import storage as atomic
from cvworkbench.cli import app
from cvworkbench.ops.publication.packet import publication_review_files
from cvworkbench.ops.publication.record import (
    ReviewReceipt,
    hash_file,
    json_bytes,
    preparation_bytes,
)
from cvworkbench.ops.syncing import SyncError, load_site_sync, sync_site
from tests.ops.publication.test_pdf import _write_docx
from tests.utils import strip_ansi


def _pdf_bytes(text: str = "Public artifact") -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    payload = document.tobytes()
    document.close()
    return payload


PDF_BYTES = _pdf_bytes()


def test_sync_api_enforces_policy_when_path_is_omitted(tmp_path: Path) -> None:
    site, config, site_config = _write_workspace(
        tmp_path, pdf_bytes=_pdf_bytes("Example Person | 555.867.5309")
    )
    before = (site / "public/cv/cv.pdf").read_bytes()
    with pytest.raises(SyncError, match="forbidden phone"):
        sync_site(config_path=config, site_config_path=site_config, mode="local")
    assert (site / "public/cv/cv.pdf").read_bytes() == before


def test_sync_api_requires_configured_publication_policy(tmp_path: Path) -> None:
    site, config, site_config = _write_workspace(tmp_path)
    (tmp_path / "publish.yaml").unlink()
    with pytest.raises(SyncError, match="Publish config not found"):
        sync_site(config_path=config, site_config_path=site_config, mode="local")
    assert (site / "public/cv/cv.pdf").read_bytes() == b"old"


def _write_workspace(
    root: Path,
    *,
    site_exists: bool = True,
    pdf_bytes: bytes = PDF_BYTES,
    contact_fields: str = "[email, location, links]",
    order: str = "[summary, experience, education]",
    manifest_pdf_hash: str | None = None,
) -> tuple[Path, Path, Path]:
    contact_field_values = [
        item.strip().strip('"') for item in contact_fields.strip("[]").split(",") if item.strip()
    ]
    order_values = [
        item.strip().strip('"') for item in order.strip("[]").split(",") if item.strip()
    ]
    (root / "local/sot").mkdir(parents=True)
    (root / "local/sot/person.yaml").write_text(
        "id: person\nname: Example Person\nphone: 555.867.5309\n"
    )
    site_repo = root / "site"
    if site_exists:
        (site_repo / "src/content/cv").mkdir(parents=True)
        (site_repo / "public/cv").mkdir(parents=True)
        (site_repo / "src/content/page-cv").mkdir(parents=True)
        (site_repo / "src/content/cv/cv.md").write_text("site-owned\n")
        (site_repo / "public/cv/cv.pdf").write_bytes(b"old")
        (site_repo / "src/content/page-cv/cv.md").write_text(
            "---\ncvPdf: /cv/old.pdf\n---\ncontent\n"
        )

    publish_dir = root / "var" / "publish" / "base"
    publish_dir.mkdir(parents=True, exist_ok=True)
    (publish_dir / "cv.pdf").write_bytes(pdf_bytes)
    authored = root / "authored.docx"
    exported = root / "exported.pdf"
    _write_docx(authored, "Public artifact")
    exported.write_bytes(pdf_bytes)
    pdf_hash = manifest_pdf_hash or hashlib.sha256(pdf_bytes).hexdigest()
    (publish_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_kind": "authored-pdf-publication",
                "variant": {
                    "id": "base",
                    "exclude_tags": ["private"],
                    "contact_fields": contact_field_values,
                    "order": order_values,
                },
                "formats": ["pdf"],
                "outputs": {"pdf": "cv.pdf"},
                "output_hashes": {"pdf": pdf_hash},
                "source": {
                    "authored_name": authored.name,
                    "authored_sha256": hash_file(authored),
                    "exported_pdf_name": exported.name,
                    "exported_pdf_sha256": hash_file(exported),
                    "pdf_token_coverage": 1.0,
                    "docx_token_coverage": 1.0,
                    "visual_fingerprint_sha256": (
                        "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
                    ),
                },
                "transformation": {
                    "kind": "semantic-redaction",
                    "forbidden_contact_fields": ["phone"],
                    "forbidden_sections": ["references"],
                    "redaction_count": 1,
                },
            }
        )
        + "\n"
    )

    workbench_config = root / "workbench.yaml"
    workbench_config.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: var/dist",
                "  publish: var/publish",
                "  runs: var/runs",
                "  sot: local/sot",
                "variants:",
                "  default: base",
                "site:",
                "  sync_mode: local",
            ]
        )
        + "\n"
    )
    variants_dir = root / "variants"
    variants_dir.mkdir()
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  exclude_tags: [private]",
                f"  contact_fields: {contact_fields}",
                f"  order: {order}",
                "  outputs: [pdf]",
            ]
        )
        + "\n"
    )
    (root / "publish.yaml").write_text(
        "\n".join(
            [
                "publish:",
                "  variants: [base]",
                "  required_exclude_tags: [private]",
                "  forbidden_contact_fields: [phone]",
                "  forbidden_sections: [references]",
                "  approved_visual_fingerprint_sha256: "
                "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
            ]
        )
        + "\n"
    )
    site_config = root / "site-sync.yaml"
    site_config.write_text(
        "\n".join(
            [
                "site:",
                f"  repo_path: {site_repo}",
                "  publish_variant: base",
                "  cv_pdf_dir: public/cv",
                "  cv_pdf_name: cv.pdf",
                "  cv_manifest: scripts/cv/public-cv-manifest.json",
                "  cv_page: src/content/page-cv/cv.md",
                "  cv_page_frontmatter_key: cvPdf",
            ]
        )
        + "\n"
    )
    if pdf_bytes.startswith(b"%PDF-"):
        # Arrange a reviewed publication; malformed artifacts remain intentionally unprepared.
        packet = publication_review_files(pdf_bytes)
        artifact_hash = hashlib.sha256(pdf_bytes).hexdigest()
        review_dir = root / "var/reviews/publication" / artifact_hash
        review_dir.mkdir(parents=True)
        for name, content in packet.items():
            (review_dir / name).write_bytes(content)
        preparation = preparation_bytes(
            authored_source=authored,
            source_pdf=exported,
            policy_path=root / "publish.yaml",
            variant_path=variants_dir / "base.yaml",
            person_path=root / "local/sot/person.yaml",
            variant="base",
            pdf_hash=artifact_hash,
            manifest_content=(publish_dir / "manifest.json").read_text(),
            review_files=packet,
            authored_hash=hash_file(authored),
            exported_hash=hash_file(exported),
        )
        (publish_dir / "preparation.json").write_bytes(preparation)
        receipt = ReviewReceipt(
            schema_version=1,
            pdf_sha256=artifact_hash,
            preparation_sha256=hashlib.sha256(preparation).hexdigest(),
            reviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        (publish_dir / "review-receipt.json").write_bytes(
            json_bytes(receipt.model_dump(mode="json"))
        )
    return site_repo, workbench_config, site_config


def _sync(root: Path, *, mode: str | None = "local"):
    _, workbench_config, site_config = _write_workspace(root)
    args = ["sync", "--config", str(workbench_config), "--site-config", str(site_config)]
    if mode is not None:
        args.extend(["--mode", mode])
    return CliRunner().invoke(app, args)


def test_site_repo_path_is_resolved_from_the_site_config_directory(tmp_path: Path) -> None:
    site_repo = tmp_path / "site"
    site_repo.mkdir()
    config_dir = tmp_path / "workbench/config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "site-sync.yaml"
    config_path.write_text(
        "site:\n"
        "  repo_path: ../../site\n"
        "  publish_variant: base\n"
        "  cv_pdf_dir: public/cv\n"
        "  cv_pdf_name: cv.pdf\n"
        "  cv_manifest: scripts/cv/public-cv-manifest.json\n"
        "  cv_page: src/content/page-cv/cv.md\n"
        "  cv_page_frontmatter_key: cvPdf\n"
    )

    assert load_site_sync(config_path).repo_path == site_repo


def test_sync_local_publishes_only_pdf_and_sanitized_manifest(tmp_path: Path) -> None:
    site_repo, workbench_config, site_config = _write_workspace(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "sync",
            "--mode",
            "local",
            "--config",
            str(workbench_config),
            "--site-config",
            str(site_config),
        ],
    )

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "sync_mode: local" in output
    assert "pdf_url: /cv/cv.pdf" in output
    assert (site_repo / "src/content/cv/cv.md").read_text() == "site-owned\n"
    assert (site_repo / "public/cv/cv.pdf").read_bytes() == PDF_BYTES
    assert "cvPdf: /cv/cv.pdf" in (site_repo / "src/content/page-cv/cv.md").read_text()
    manifest_text = (site_repo / "scripts/cv/public-cv-manifest.json").read_text()
    manifest = json.loads(manifest_text)
    assert manifest == {
        "schema_version": 1,
        "variant": "base",
        "pdf_path": "public/cv/cv.pdf",
        "pdf_sha256": hashlib.sha256(PDF_BYTES).hexdigest(),
        "required_exclude_tags": ["private"],
        "forbidden_contact_fields": ["phone"],
        "forbidden_sections": ["references"],
    }
    assert '"forbidden_contact_fields": ["phone"]' in manifest_text
    assert '"forbidden_sections": ["references"]' in manifest_text
    assert '"required_exclude_tags": ["private"]' in manifest_text


def test_sync_copies_the_validated_pdf_when_source_changes_after_planning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cvworkbench.ops import syncing

    site, config, site_config = _write_workspace(tmp_path)
    source = tmp_path / "var/publish/base/cv.pdf"
    original_plan = syncing._plan_sync
    unreviewed = _pdf_bytes("Unreviewed contact 555.867.5309")

    def change_source_after_planning(*args, **kwargs):
        plan = original_plan(*args, **kwargs)
        source.write_bytes(unreviewed)
        return plan

    monkeypatch.setattr(syncing, "_plan_sync", change_source_after_planning)
    sync_site(config_path=config, site_config_path=site_config, mode="local")

    assert source.read_bytes() == unreviewed
    assert (site / "public/cv/cv.pdf").read_bytes() == PDF_BYTES
    manifest = json.loads((site / "scripts/cv/public-cv-manifest.json").read_text())
    assert manifest["pdf_sha256"] == hashlib.sha256(PDF_BYTES).hexdigest()


def test_sync_rejects_a_review_for_a_different_publication_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cvworkbench.ops import syncing
    from cvworkbench.ops.publication.pdf import prepare_public_pdf
    from cvworkbench.ops.publication.state import record_publication_review

    site, config, site_config = _write_workspace(tmp_path)
    inspect = syncing.inspect_publication

    def prepare_and_review_another_generation(*args, **kwargs):
        authored = tmp_path / "authored.docx"
        exported = tmp_path / "exported.pdf"
        _write_docx(authored, "Public artifact revised")
        exported.write_bytes(_pdf_bytes("Public artifact revised"))
        prepare_public_pdf(
            authored_source=authored,
            source_pdf=exported,
            config_path=config,
            variant_id="base",
            publish_config_path=tmp_path / "publish.yaml",
            sot_path=tmp_path / "local/sot",
        )
        updated = inspect(*args, **kwargs)
        assert updated.pdf_sha256 != hashlib.sha256(PDF_BYTES).hexdigest()
        record_publication_review(config, "base", updated.pdf_sha256)
        return inspect(*args, **kwargs)

    monkeypatch.setattr(syncing, "inspect_publication", prepare_and_review_another_generation)
    with pytest.raises(SyncError, match="Reviewed PDF does not match captured artifact"):
        sync_site(config_path=config, site_config_path=site_config, mode="local")

    assert (site / "public/cv/cv.pdf").read_bytes() == b"old"
    assert not (site / "scripts/cv/public-cv-manifest.json").exists()


def test_sync_local_rolls_back_every_artifact_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site_repo, workbench_config, site_config = _write_workspace(tmp_path)
    manifest_path = site_repo / "scripts/cv/public-cv-manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("old manifest\n")
    destinations = {
        site_repo / "public/cv/cv.pdf": b"old",
        site_repo / "src/content/page-cv/cv.md": (
            site_repo / "src/content/page-cv/cv.md"
        ).read_bytes(),
        manifest_path: b"old manifest\n",
    }
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

    result = CliRunner().invoke(
        app,
        ["sync", "--config", str(workbench_config), "--site-config", str(site_config)],
    )

    assert result.exit_code != 0
    assert "prior artifacts were restored" in strip_ansi(result.stderr)
    for destination, original in destinations.items():
        assert destination.read_bytes() == original
    assert not list(site_repo.rglob("*.cvw-stage-*"))
    assert not list(site_repo.rglob("*.cvw-backup-*"))


def test_sync_local_preserves_existing_destination_permissions(tmp_path: Path) -> None:
    site_repo, workbench_config, site_config = _write_workspace(tmp_path)
    page_path = site_repo / "src/content/page-cv/cv.md"
    manifest_path = site_repo / "scripts/cv/public-cv-manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("old manifest\n")
    page_path.chmod(0o644)
    manifest_path.chmod(0o640)

    result = CliRunner().invoke(
        app,
        ["sync", "--config", str(workbench_config), "--site-config", str(site_config)],
    )

    assert result.exit_code == 0
    assert page_path.stat().st_mode & 0o777 == 0o644
    assert manifest_path.stat().st_mode & 0o777 == 0o640


def test_sync_defaults_to_config_mode(tmp_path: Path) -> None:
    result = _sync(tmp_path, mode=None)

    assert result.exit_code == 0
    assert "sync_mode: local" in strip_ansi(result.stdout)


def test_sync_fails_when_repo_path_missing(tmp_path: Path) -> None:
    _, workbench_config, site_config = _write_workspace(tmp_path, site_exists=False)

    result = CliRunner().invoke(
        app,
        [
            "sync",
            "--mode",
            "local",
            "--config",
            str(workbench_config),
            "--site-config",
            str(site_config),
        ],
    )

    assert result.exit_code != 0
    assert "Site repo path not found" in strip_ansi(result.stderr)


def test_sync_rejects_non_pdf_artifact(tmp_path: Path) -> None:
    _, workbench_config, site_config = _write_workspace(tmp_path, pdf_bytes=b"LaTeX source")

    result = CliRunner().invoke(
        app,
        ["sync", "--config", str(workbench_config), "--site-config", str(site_config)],
    )

    assert result.exit_code != 0
    assert "not a PDF" in strip_ansi(result.stderr)


def test_sync_rejects_artifact_hash_mismatch(tmp_path: Path) -> None:
    _, workbench_config, site_config = _write_workspace(tmp_path, manifest_pdf_hash="0" * 64)

    result = CliRunner().invoke(
        app,
        ["sync", "--config", str(workbench_config), "--site-config", str(site_config)],
    )

    assert result.exit_code != 0
    assert "hash does not match" in strip_ansi(result.stderr)


def test_sync_rejects_regular_build_manifest_without_authored_provenance(
    tmp_path: Path,
) -> None:
    _, workbench_config, site_config = _write_workspace(tmp_path)
    manifest_path = tmp_path / "var/publish/base/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.pop("artifact_kind")
    manifest_path.write_text(json.dumps(manifest) + "\n")

    result = CliRunner().invoke(
        app,
        ["sync", "--config", str(workbench_config), "--site-config", str(site_config)],
    )

    assert result.exit_code != 0
    assert "not an authored PDF publication" in strip_ansi(result.stderr)


def test_sync_rejects_manifest_with_unapproved_visual_fingerprint(tmp_path: Path) -> None:
    _, workbench_config, site_config = _write_workspace(tmp_path)
    manifest_path = tmp_path / "var/publish/base/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["source"]["visual_fingerprint_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest) + "\n")

    result = CliRunner().invoke(
        app,
        ["sync", "--config", str(workbench_config), "--site-config", str(site_config)],
    )

    assert result.exit_code != 0
    assert "visual fingerprint does not match" in strip_ansi(result.stderr)


def test_sync_rejects_manifest_destination_outside_site_repo(tmp_path: Path) -> None:
    _, workbench_config, site_config = _write_workspace(tmp_path)
    site_config.write_text(
        site_config.read_text().replace(
            "cv_manifest: scripts/cv/public-cv-manifest.json",
            "cv_manifest: ../outside.json",
        )
    )

    result = CliRunner().invoke(
        app,
        ["sync", "--config", str(workbench_config), "--site-config", str(site_config)],
    )

    assert result.exit_code != 0
    assert "must remain inside the site repository" in strip_ansi(result.stderr)
    assert not (tmp_path / "outside.json").exists()


def test_sync_rejects_public_variant_with_forbidden_contact_field(tmp_path: Path) -> None:
    _, workbench_config, site_config = _write_workspace(
        tmp_path, contact_fields='["email", "phone"]'
    )

    result = CliRunner().invoke(
        app,
        ["sync", "--config", str(workbench_config), "--site-config", str(site_config)],
    )

    assert result.exit_code != 0
    assert "forbidden contact fields" in strip_ansi(result.stderr)


def test_sync_rejects_public_variant_with_forbidden_section(tmp_path: Path) -> None:
    _, workbench_config, site_config = _write_workspace(tmp_path, order='["summary", "references"]')

    result = CliRunner().invoke(
        app,
        ["sync", "--config", str(workbench_config), "--site-config", str(site_config)],
    )

    assert result.exit_code != 0
    assert "forbidden sections" in strip_ansi(result.stderr)
