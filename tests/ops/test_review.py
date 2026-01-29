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


def _write_minimal_config(root: Path) -> Path:
    config_dir = root / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    workbench = config_dir / "workbench.yaml"
    workbench.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: dist",
                "  runs: runs",
                "  sot: sot",
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


def test_reviewpack_creates_bundle(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    dist_dir = tmp_path / "config" / "dist" / "base"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "cv.docx").write_bytes(b"docx")
    (dist_dir / "cv.pdf").write_bytes(b"pdf")
    (dist_dir / "selection.json").write_text(
        '{"items":[{"id":"b1","type":"bullet","included":true,"text":"x","role_id":"r1"}]}'
    )

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(
            app,
            ["reviewpack", "--variant", "base", "--config", str(config_path), "--plain"],
        )

    assert result.exit_code == 0
    out_dir = Path(cwd) / "reviews" / "base"
    assert (out_dir / "cv.docx").exists()
    assert (out_dir / "cv.pdf").exists()
    assert (out_dir / "review.md").exists()


def test_import_docx_writes_patch(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_minimal_config(tmp_path)
    runs_dir = tmp_path / "config" / "runs" / "2026-01-01T00-00-00Z"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "canonical.md").write_text("before\n")

    docx_path = tmp_path / "review.docx"
    docx_path.write_bytes(b"docx")

    def fake_convert(_path: Path) -> str:
        return "after\n"

    monkeypatch.setattr(review_module, "_convert_docx_to_markdown", fake_convert)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
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
    drafts_dir = Path(cwd) / "drafts"
    assert drafts_dir.exists()
    patch_files = list(drafts_dir.rglob("patch.diff"))
    assert patch_files
