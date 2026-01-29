"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_render_formats.py

Tests additional render formats.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


def test_render_writes_html_and_docx(tmp_path: Path) -> None:
    canonical_path = tmp_path / "canonical.md"
    canonical_path.write_text("# Sample\n")

    html_path = Path("dist/base/cv.html")
    docx_path = Path("dist/base/cv.docx")
    for path in [html_path, docx_path]:
        if path.exists():
            path.unlink()

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "render",
            "--canonical",
            str(canonical_path),
            "--variant",
            "base",
            "--format",
            "html,docx",
        ],
    )

    assert result.exit_code == 0
    assert html_path.exists()
    assert docx_path.exists()
    assert html_path.stat().st_size > 0
    assert docx_path.stat().st_size > 0
