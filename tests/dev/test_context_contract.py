"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/dev/test_context_contract.py

Tests compact context docs/help contract for bootstrap usage.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app
from tests.utils import strip_ansi

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_context_help_exposes_compact_bootstrap_mode() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["context", "--help"])

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "--compact" in output
    assert "summary-only JSON output" in output
    assert "agent handoff" in output


def test_workflow_help_exposes_compact_recipe_mode() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["workflow", "--help"])

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "--compact" in output
    assert "recipe retrieval" in output
    assert "agent handoff" in output


def test_compact_bootstrap_docs_match_live_commands() -> None:
    readme = (REPO_ROOT / "README.md").read_text()
    quickstart = (REPO_ROOT / "docs" / "howto" / "quickstart.md").read_text()
    contract = (REPO_ROOT / "docs" / "reference" / "context-contract.md").read_text()

    assert "uv run cvw context --json --compact" in readme
    assert "uv run cvw workflow --id automation.verify" in readme
    assert "uv run cvw workflow --id automation.verify --json --compact" in readme
    assert "uv run cvw context --json --compact" in quickstart
    assert "uv run cvw workflow --id automation.verify" in quickstart
    assert "uv run cvw workflow --id automation.verify --json --compact" in quickstart
    assert "recommended_workflows" in contract
    assert "json_command" in contract
    assert "local bootstrap lane" in contract
    assert "repair.sot_path" in contract
    assert "repair.sot_yaml" in contract
    assert "uv run cvw context --json --compact" in contract
    assert "uv run cvw workflow --id <recipe-id> --json --compact" in contract
