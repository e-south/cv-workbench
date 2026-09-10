"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/workspace/test_status.py

Tests status data and source diagnostics independently of terminal presentation.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.config import read_config
from cvworkbench.ops.scaffold import init_project
from tests.workspace.test_configuration import _populated_workspace


def test_status_api_reports_workspace_without_output_or_writes(tmp_path, capsys):
    from cvworkbench.workspace.status import inspect_status

    config = _populated_workspace(tmp_path)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    status = inspect_status(config=config, sot_path=None)
    assert status["sot"]["path"] == str(tmp_path / "sot.sample")
    assert status["sot"]["sections"]["experience"]["roles"] > 0
    assert status["variants"]["config_count"] == 2
    assert status["variants"]["inbox_count"] == 1
    assert status["runs"]["latest_by_variant"]["base"][0]["formats"] == ["md"]
    assert status["projects"]["items"][0]["project_id"] == "research"
    assert status["reviews"]["items"][0]["missing_files"] == ["cv.pdf", "cv.docx"]
    assert status["publication"]["state"] == "untracked"
    assert "command" not in status
    assert inspect_status(config=config, sot_path=None) == status
    assert {
        p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    } == before
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_status_api_can_reuse_captured_settings(tmp_path):
    from cvworkbench.workspace.status import inspect_status

    config = _populated_workspace(tmp_path)
    expected = inspect_status(config=config, sot_path=None)
    snapshot = read_config(config)
    config.unlink()
    assert inspect_status(config=snapshot, sot_path=None) == expected


def test_status_source_diagnostics_remain_structured_and_quiet(tmp_path, capsys):
    from cvworkbench.workspace.status import StatusInspectionError, inspect_status

    init_project(tmp_path, sample_default=True)
    config = tmp_path / "config/workbench.yaml"
    (tmp_path / "sot.sample/person.yaml").unlink()
    (tmp_path / "sot.sample/experience.yaml").unlink()
    with pytest.raises(StatusInspectionError) as failure:
        inspect_status(config=config, sot_path=None)
    assert len(failure.value.errors) == 2
    assert any("person.yaml" in error for error in failure.value.errors)
    assert any("experience.yaml" in error for error in failure.value.errors)
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""

    result = CliRunner().invoke(app, ["status", "--config", str(config)])
    assert result.exit_code == 1
    assert result.stderr == "".join(f"ERROR: {error}\n" for error in failure.value.errors)


def test_status_reports_missing_configuration_with_an_actionable_cli_error(tmp_path: Path):
    config = tmp_path / "missing.yaml"
    result = CliRunner().invoke(app, ["status", "--config", str(config)])
    assert result.exit_code == 1
    assert result.stderr == f"ERROR: Config file not found: {config}\n"


def test_status_accepts_explicit_source_without_a_default_build_variant(tmp_path):
    import yaml

    from cvworkbench.workspace.status import inspect_status

    init_project(tmp_path, sample_default=True)
    config = tmp_path / "config/workbench.yaml"
    data = yaml.safe_load(config.read_text())
    data.pop("variants")
    data["paths"]["sot"] = "../missing"
    config.write_text(yaml.safe_dump(data))
    status = inspect_status(config=config, sot_path=tmp_path / "sot.sample")
    assert status["sot"]["path"] == str(tmp_path / "sot.sample")
    assert status["variants"]["config_count"] == 2
