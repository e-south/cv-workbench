"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_render.py

Tests render command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app

from tests.utils import strip_ansi

def test_render_writes_output(tmp_path: Path) -> None:
    canonical_path = tmp_path / "canonical.md"
    canonical_path.write_text("# Sample\n")

    output_path = Path("dist/base/cv.md")
    if output_path.exists():
        output_path.unlink()

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
            "md",
        ],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    output = strip_ansi(result.stdout)
    assert "output_md:" in output
    assert "cv.md" in output
