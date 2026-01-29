"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_cli_output_modes.py

Tests CLI output modes.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from cvworkbench.cli import app


def test_build_plain_output() -> None:
    runner = CliRunner()

    result = runner.invoke(
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
        ],
    )

    assert result.exit_code == 0
    assert "output_md:" in result.stdout
    assert "cv.md" in result.stdout
    assert "╭" not in result.stdout


def test_build_json_output() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "build",
            "--json",
            "--variant",
            "base",
            "--format",
            "md",
            "--sot-path",
            "sot.sample",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "build"
    assert "output_md" in payload["data"]
