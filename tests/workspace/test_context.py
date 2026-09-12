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
import yaml

from cvworkbench.ops.scaffold import init_project
from cvworkbench.ops.sot_versions import initialize_pack
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


@pytest.mark.parametrize("selection", [None, b"\xff"])
def test_pinned_source_reports_damaged_pack_metadata_as_an_issue(
    tmp_path: Path, selection: bytes | None
) -> None:
    init_project(tmp_path, sample_default=True)
    pack = initialize_pack(source=tmp_path / "sot.sample", destination=tmp_path / "pack")
    active = pack.root / "ACTIVE"
    if selection is None:
        active.unlink()
    else:
        active.write_bytes(selection)
    config = tmp_path / "config/workbench.yaml"
    settings = yaml.safe_load(config.read_text())
    settings["paths"]["sot"] = str(pack.version)
    config.write_text(yaml.safe_dump(settings, sort_keys=False))
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    result = inspect_workspace(config=config, sot_path=None, strict=False)

    assert result["sot"]["status"] == "ready"
    assert result["sot"]["path"] == str(pack.version)
    assert any("Active SoT" in issue for issue in result["issues"])
    with pytest.raises(ValueError, match="Active SoT"):
        inspect_workspace(config=config, sot_path=None, strict=True)
    assert {
        p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    } == before
