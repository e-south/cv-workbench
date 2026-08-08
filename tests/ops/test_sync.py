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
from pathlib import Path

import pymupdf
import pytest
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.ops import syncing
from cvworkbench.ops.syncing import load_site_sync
from tests.utils import strip_ansi


def _pdf_bytes(text: str = "Public artifact") -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    payload = document.tobytes()
    document.close()
    return payload


PDF_BYTES = _pdf_bytes()


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
    replace = syncing.os.replace
    staged_replacements = 0

    def fail_second_staged_replace(source: Path | str, destination: Path | str) -> None:
        nonlocal staged_replacements
        if ".cvw-stage-" in Path(source).name:
            staged_replacements += 1
            if staged_replacements == 2:
                raise OSError("simulated replacement failure")
        replace(source, destination)

    monkeypatch.setattr(syncing.os, "replace", fail_second_staged_replace)

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
