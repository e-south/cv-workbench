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


def test_build_writes_selection() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["build", "--plain", "--variant", "base", "--format", "md", "--sot-path", "sot.sample"],
    )
    assert result.exit_code == 0
    selection_path = Path("dist/base/selection.json")
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
