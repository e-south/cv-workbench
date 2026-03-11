"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_selection.py

Tests selection metadata and explain command.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


def _write_build_config(root: Path) -> Path:
    config_dir = root / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md]",
            ]
        )
        + "\n"
    )
    themes_dir = Path(__file__).resolve().parents[2] / "build" / "themes"
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: ../var/dist",
                "  runs: ../var/runs",
                "variants:",
                "  default: base",
                "render:",
                f"  themes_dir: {themes_dir}",
                "  theme: default",
                "  style_preset: modern",
            ]
        )
        + "\n"
    )
    return config_path


def test_build_writes_selection() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["build", "--plain", "--variant", "base", "--format", "md", "--sot-path", "sot.sample"],
    )
    assert result.exit_code == 0
    selection_path = Path("var/dist/base/selection.json")
    payload = json.loads(selection_path.read_text())
    assert isinstance(payload.get("items"), list)


def test_explain_outputs_selection_item() -> None:
    runner = CliRunner()
    runner.invoke(
        app,
        ["build", "--plain", "--variant", "base", "--format", "md", "--sot-path", "sot.sample"],
    )
    result = runner.invoke(
        app,
        ["explain", "--variant", "base", "--id", "acme-01", "--plain"],
    )
    assert result.exit_code == 0
    assert "acme-01" in result.stdout


def test_dist_selection_is_deterministic_across_repeated_builds(tmp_path: Path) -> None:
    config_path = _write_build_config(tmp_path)
    runner = CliRunner()

    first = runner.invoke(
        app,
        [
            "build",
            "--plain",
            "--variant",
            "base",
            "--format",
            "md",
            "--sot-path",
            "sot.sample",
            "--config",
            str(config_path),
        ],
    )
    assert first.exit_code == 0
    selection_path = tmp_path / "var" / "dist" / "base" / "selection.json"
    first_selection = selection_path.read_text()

    second = runner.invoke(
        app,
        [
            "build",
            "--plain",
            "--variant",
            "base",
            "--format",
            "md",
            "--sot-path",
            "sot.sample",
            "--config",
            str(config_path),
        ],
    )
    assert second.exit_code == 0
    second_selection = selection_path.read_text()

    assert first_selection == second_selection
    assert "created_at" not in json.loads(second_selection)
