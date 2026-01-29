"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/test_cli.py

Tests the CLI surface and validation behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


def test_cli_help_lists_commands() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "validate" in result.stdout
    assert "build" in result.stdout
    assert "render" in result.stdout
    assert "tailor" in result.stdout
    assert "diff" in result.stdout
    assert "sync" in result.stdout


def test_validate_succeeds_with_sample_sot() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["validate", "--sot-path", "sot.sample"])

    assert result.exit_code == 0


def test_validate_fails_on_missing_required_file(tmp_path: Path) -> None:
    (tmp_path / "person.yaml").write_text("id: sample\nname: Sample\n")

    runner = CliRunner()

    result = runner.invoke(app, ["validate", "--sot-path", str(tmp_path)])

    assert result.exit_code != 0
    assert "experience.yaml" in result.stderr


def test_build_prints_output_locations() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["build", "--variant", "base", "--format", "md", "--sot-path", "sot.sample"],
    )

    assert result.exit_code == 0
    assert "output_md:" in result.stdout
    assert "cv.md" in result.stdout
    assert "run_dir:" in result.stdout
