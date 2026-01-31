"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_context.py

Tests context command output.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


def _write_config(root: Path) -> Path:
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
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  runs: ../var/runs",
                "  projects: ../var/projects",
                "  reviews: ../var/reviews",
                "variants:",
                "  default: base",
                "variant_lifecycle:",
                "  ttl_days: 7",
            ]
        )
        + "\n"
    )
    return config_path


def test_context_reports_missing_sot_and_recipes(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "context",
            "--json",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "context"
    assert payload["sot"]["status"] == "missing"
    assert payload["variants"]["config_count"] == 1
    assert payload["recipes"]
    recipe_ids = [recipe["id"] for recipe in payload["recipes"]]
    assert recipe_ids[:3] == ["baseline.build_preview", "review.import", "project.guide"]
    for recipe in payload["recipes"][:3]:
        assert "preconditions" in recipe
        assert "steps" in recipe
        assert "outputs" in recipe
        assert "stop_conditions" in recipe
        assert recipe["steps"]
        assert "command" in recipe["steps"][0]


def test_context_strict_requires_sot(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "context",
            "--json",
            "--strict",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 1
