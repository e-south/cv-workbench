"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/test_doctor.py

Tests doctor command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from typer.testing import CliRunner

import cvworkbench.doctor as doctor_module
from cvworkbench.cli import app


def test_doctor_reports_dependencies(monkeypatch) -> None:
    def fake_run_command(*_args, **_kwargs):
        return 0, "pandoc 3.1.0"

    monkeypatch.setattr(doctor_module, "_run_command", fake_run_command)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor", "--plain"])

    assert result.exit_code == 0
    assert "pandoc" in result.stdout
    assert "xelatex" in result.stdout


def test_doctor_fails_when_missing_dependency(monkeypatch) -> None:
    def fake_run_command(command, *_args, **_kwargs):
        if command == "xelatex":
            raise FileNotFoundError(command)
        return 0, "pandoc 3.1.0"

    monkeypatch.setattr(doctor_module, "_run_command", fake_run_command)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor", "--plain"])

    assert result.exit_code != 0
    assert "xelatex" in result.stderr
