"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_review.py

Tests reviewpack and import-docx commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import cvworkbench.ops.review as review_module
from cvworkbench.cli import app
from cvworkbench.config import resolve_drafts_path, resolve_reviews_path


def _write_minimal_config(root: Path) -> Path:
    config_dir = root / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    workbench = config_dir / "workbench.yaml"
    workbench.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: ../var/dist",
                "  runs: ../var/runs",
                "  sot: ../local/sot",
                "variants:",
                "  default: base",
            ]
        )
        + "\n"
    )
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md, pdf, docx]",
            ]
        )
        + "\n"
    )
    return workbench


def _write_run_manifest(root: Path, run_id: str, variant_id: str, canonical: str) -> None:
    run_dir = root / "var" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "canonical.md").write_text(canonical)
    (run_dir / "manifest.json").write_text(
        "\n".join(
            [
                "{",
                f'  "created_at": "2026-01-01T00:00:00+00:00",',
                '  "formats": ["md"],',
                '  "outputs": {"md": "cv.md"},',
                f'  "variant": {{"id": "{variant_id}"}},',
                '  "resume": {"path": "resume.json", "hash": "hash"}',
                "}",
            ]
        )
        + "\n"
    )


def test_reviewpack_creates_bundle(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    dist_dir = tmp_path / "var" / "dist" / "base"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "cv.docx").write_bytes(b"docx")
    (dist_dir / "cv.pdf").write_bytes(b"pdf")
    (dist_dir / "selection.json").write_text(
        '{"items":[{"id":"b1","type":"bullet","included":true,"text":"x","role_id":"r1"}]}'
    )
    _write_run_manifest(tmp_path, "2026-01-01T00-00-00Z", "base", "before\n")

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            ["reviewpack", "--variant", "base", "--config", str(config_path), "--plain"],
        )

    assert result.exit_code == 0
    out_dir = resolve_reviews_path(config_path) / "base"
    assert (out_dir / "cv.docx").exists()
    assert (out_dir / "cv.pdf").exists()
    assert (out_dir / "review.md").exists()


def test_reviewpack_requires_runs(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    dist_dir = tmp_path / "var" / "dist" / "base"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "cv.docx").write_bytes(b"docx")
    (dist_dir / "cv.pdf").write_bytes(b"pdf")
    (dist_dir / "selection.json").write_text(
        '{"items":[{"id":"b1","type":"bullet","included":true,"text":"x","role_id":"r1"}]}'
    )

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            ["reviewpack", "--variant", "base", "--config", str(config_path), "--plain"],
        )

    assert result.exit_code != 0
    assert "No runs available" in (result.stderr or "")


def test_import_docx_writes_patch(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_run_manifest(tmp_path, "2026-01-01T00-00-00Z", "base", "before\n")

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return "after\n"

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--run",
                "2026-01-01T00-00-00Z",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    drafts_dir = resolve_drafts_path(config_path)
    assert drafts_dir.exists()
    patch_files = list(drafts_dir.rglob("patch.diff"))
    assert patch_files


def test_import_docx_uses_variant_latest_run(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_minimal_config(tmp_path)
    _write_run_manifest(tmp_path, "2026-01-01T00-00-00Z", "base", "base-before\n")
    _write_run_manifest(tmp_path, "2026-01-02T00-00-00Z", "cover", "cover-before\n")

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return "after\n"

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "import-docx",
                "--from",
                str(docx_path),
                "--variant",
                "base",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    drafts_dir = resolve_drafts_path(config_path)
    patch_files = list(drafts_dir.rglob("patch.diff"))
    assert patch_files
    patch_text = patch_files[0].read_text()
    assert "base-before" in patch_text
