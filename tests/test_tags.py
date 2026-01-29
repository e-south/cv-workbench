"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/test_tags.py

Tests tags command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from typer.testing import CliRunner

from cvworkbench.cli import app


def test_tags_list_outputs_known_tag() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["tags", "list", "--plain", "--sot-path", "sot.sample"])
    assert result.exit_code == 0
    assert "infra" in result.stdout


def test_tags_stats_outputs_counts() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["tags", "stats", "--plain", "--sot-path", "sot.sample"])
    assert result.exit_code == 0
    assert "infra:" in result.stdout


def test_tags_lint_ok() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["tags", "lint", "--plain", "--sot-path", "sot.sample"])
    assert result.exit_code == 0
    assert "ok" in result.stdout
