"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_diff.py

Tests diff command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app
from tests.utils import strip_ansi


def test_diff_resume_json_output() -> None:
    runs_root = Path("runs")
    run_a = runs_root / "2026-01-01T00-00-00Z"
    run_b = runs_root / "2026-01-02T00-00-00Z"
    run_a.mkdir(parents=True, exist_ok=True)
    run_b.mkdir(parents=True, exist_ok=True)

    (run_a / "resume.json").write_text('{"basics": {"name": "Alpha"}}\n')
    (run_b / "resume.json").write_text('{"basics": {"name": "Beta"}}\n')

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "diff",
            "--artifact",
            "resume",
            "--run-a",
            str(run_a),
            "--run-b",
            str(run_b),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["equal"] is False
    assert payload["a"]["artifact"] == "resume"


def test_diff_unified_prints_summary() -> None:
    runs_root = Path("runs")
    run_a = runs_root / "2026-01-03T00-00-00Z"
    run_b = runs_root / "2026-01-04T00-00-00Z"
    run_a.mkdir(parents=True, exist_ok=True)
    run_b.mkdir(parents=True, exist_ok=True)

    (run_a / "resume.json").write_text('{"basics": {"name": "Alpha"}}\n')
    (run_b / "resume.json").write_text('{"basics": {"name": "Beta"}}\n')

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "diff",
            "--artifact",
            "resume",
            "--run-a",
            str(run_a),
            "--run-b",
            str(run_b),
        ],
    )

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "additions:" in output
    assert "deletions:" in output
    assert "equal:" in output
