"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_clean.py

Tests cleanup command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


def _write_minimal_config(root: Path) -> Path:
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    workbench = config_dir / "workbench.yaml"
    workbench.write_text(
        "\n".join(
            [
                "paths:",
                "  runs: ../runs",
                "  dist: ../dist",
                "  drafts: ../drafts",
                "variants:",
                "  default: base",
            ]
        )
        + "\n"
    )
    return workbench


def test_clean_runs_requires_confirmation(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    runs_dir = tmp_path / "runs" / "run1"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "canonical.md").write_text("test")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "clean",
            "runs",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 2
    assert runs_dir.exists()
    assert "status:" in result.stdout


def test_clean_runs_deletes_contents(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    runs_dir = tmp_path / "runs" / "run1"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "canonical.md").write_text("test")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "clean",
            "runs",
            "--config",
            str(config_path),
            "--yes",
            "--plain",
        ],
    )

    assert result.exit_code == 0
    assert (tmp_path / "runs").exists()
    assert not runs_dir.exists()
    assert "status:" in result.stdout
