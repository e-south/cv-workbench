"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_theme.py

Tests theme CLI commands.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from typer.testing import CliRunner

from cvworkbench.cli import app


def test_theme_list_reports_default_theme() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["theme", "list", "--plain"])

    assert result.exit_code == 0
    assert "themes:" in result.stdout
    assert "default" in result.stdout


def test_theme_info_reports_routes() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["theme", "info", "default", "--plain"])

    assert result.exit_code == 0
    assert "id: default" in result.stdout
    assert "routes:" in result.stdout
