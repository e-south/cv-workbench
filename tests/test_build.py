"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/test_build.py

Tests build pipeline behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


def test_build_generates_markdown() -> None:
    output_path = Path("dist/base/cv.md")
    if output_path.exists():
        output_path.unlink()

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["build", "--variant", "base", "--format", "md", "--sot-path", "sot.sample"],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    content = output_path.read_text()
    assert "Alex Example" in content
    assert ".tag-" not in content


def test_build_marks_publication_roles() -> None:
    output_path = Path("dist/base/cv.md")
    if output_path.exists():
        output_path.unlink()

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["build", "--variant", "base", "--format", "md", "--sot-path", "sot.sample"],
    )

    assert result.exit_code == 0
    content = output_path.read_text()
    assert "Alex Example\\*" in content
