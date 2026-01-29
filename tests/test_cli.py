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

from tests.utils import strip_ansi


def test_cli_help_lists_commands() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "validate" in output
    assert "init" in output
    assert "quickstart" in output
    assert "doctor" in output
    assert "build" in output
    assert "render" in output
    assert "tailor" in output
    assert "diff" in output
    assert "sync" in output
    assert "explain" in output
    assert "reviewpack" in output
    assert "import-docx" in output
    assert "job" in output
    assert "tags" in output


def test_validate_succeeds_with_sample_sot() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["validate", "--sot-path", "sot.sample"])

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "status:" in output
    assert "sot_path:" in output


def test_validate_fails_on_missing_required_file(tmp_path: Path) -> None:
    (tmp_path / "person.yaml").write_text("id: sample\nname: Sample\n")

    runner = CliRunner()

    result = runner.invoke(app, ["validate", "--sot-path", str(tmp_path)])

    assert result.exit_code != 0
    assert "experience.yaml" in result.stderr


def test_tailor_prints_draft_paths(tmp_path: Path) -> None:
    job_path = tmp_path / "job.md"
    job_path.write_text("Role: Test\nNeeds: Python\n")
    draft_dir = tmp_path / "drafts" / "sample-role"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "tailor",
            "--job",
            str(job_path),
            "--out",
            str(draft_dir),
            "--base-variant",
            "base",
        ],
    )

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "draft_dir:" in output
    assert "variant:" in output
    assert "patch:" in output


def test_apply_prints_status(tmp_path: Path) -> None:
    draft_dir = tmp_path / "draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / "patch.diff").write_text("")
    sot_dir = tmp_path / "sot"
    sot_dir.mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "apply",
            "--draft",
            str(draft_dir),
            "--sot-path",
            str(sot_dir),
        ],
    )

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "status:" in output
    assert "no_changes" in output


def test_build_prints_output_locations() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["build", "--variant", "base", "--format", "md", "--sot-path", "sot.sample"],
    )

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "output_md:" in output
    assert "cv.md" in output
    assert "run_dir:" in output
