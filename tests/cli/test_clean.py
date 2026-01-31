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

import pytest
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
                "  runs: ../var/runs",
                "  dist: ../var/dist",
                "  drafts: ../var/drafts",
                "  registry: ../var/registry",
                "  reviews: ../var/reviews",
                "  projects: ../var/projects",
                "variants:",
                "  default: base",
            ]
        )
        + "\n"
    )
    return workbench


def test_clean_runs_requires_confirmation(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)
    runs_dir = tmp_path / "var" / "runs" / "run1"
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
    runs_dir = tmp_path / "var" / "runs" / "run1"
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
    assert (tmp_path / "var" / "runs").exists()
    assert not runs_dir.exists()
    assert "status:" in result.stdout


def test_clean_runs_refuses_outside_var(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  runs: ../runs",
                "variants:",
                "  default: base",
            ]
        )
        + "\n"
    )
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

    assert result.exit_code == 1
    assert "outside var" in result.stderr


@pytest.mark.parametrize(
    ("target", "relative_dir", "filename"),
    [
        ("registry", Path("var/registry/contexts/context-1"), "source.json"),
        ("reviews", Path("var/reviews/base"), "review.md"),
        ("projects", Path("var/projects/demo"), "project.yaml"),
    ],
)
def test_clean_additional_targets(
    tmp_path: Path,
    target: str,
    relative_dir: Path,
    filename: str,
) -> None:
    config_path = _write_minimal_config(tmp_path)
    target_dir = tmp_path / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / filename).write_text("test")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "clean",
            target,
            "--config",
            str(config_path),
            "--yes",
            "--plain",
        ],
    )

    assert result.exit_code == 0
    assert not target_dir.exists()
