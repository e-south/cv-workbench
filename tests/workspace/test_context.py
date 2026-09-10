"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/workspace/test_context.py

Tests workspace inspection without command-line presentation side effects.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from pathlib import Path

import pytest

from cvworkbench.ops.scaffold import init_project
from cvworkbench.workspace.context import inspect_workspace


def test_workspace_inspection_is_quiet_read_only_and_repeatable(tmp_path: Path, capsys) -> None:
    init_project(tmp_path, sample_default=True)
    config = tmp_path / "config" / "workbench.yaml"
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    first = inspect_workspace(config=config, sot_path=None, strict=True)
    second = inspect_workspace(config=config, sot_path=None, strict=True)

    assert first == second
    assert first["sot"]["status"] == "ready"
    assert first["variants"]["default"] == "base"
    assert first["issues"] == []
    assert "command" not in first
    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert before == after
    output = capsys.readouterr()
    assert output.out == output.err == ""


def test_strict_workspace_inspection_raises_without_terminal_output(tmp_path: Path, capsys) -> None:
    config = tmp_path / "config" / "workbench.yaml"
    config.parent.mkdir()
    config.write_text("paths:\n  sot: ../missing\nvariants:\n  default: base\n")

    with pytest.raises(ValueError, match="SoT path not found"):
        inspect_workspace(config=config, sot_path=None, strict=True)
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == ""
