"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/workspace/projects/test_inspection.py

Verify project inspection contracts across configuration changes and presentation.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.config import read_config
from cvworkbench.ops.projects import guide_project
from cvworkbench.ops.scaffold import init_project
from cvworkbench.workspace.projects import inspect_project, inspect_project_preview


@pytest.fixture
def guided_project(tmp_path):
    init_project(tmp_path, sample_default=True)
    config = tmp_path / "config/workbench.yaml"
    job = tmp_path / "job.txt"
    job.write_text("Research scientist with Python and engineering experience.\n")
    paths = guide_project(
        config_path=config, job_file=job, variant_id="base", slug="research"
    ).paths
    result = CliRunner().invoke(
        app,
        [
            "build",
            "--project",
            str(paths.project_dir),
            "--config",
            str(config),
            "--format",
            "md",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    return config, paths


@pytest.mark.parametrize("entrypoint", ["api", "cli"])
@pytest.mark.parametrize("mutation", ["edit", "remove"])
def test_project_inspection_uses_one_configuration_generation(
    guided_project, monkeypatch, entrypoint, mutation
):
    config, paths = guided_project
    project_id = paths.project_dir.name

    def inspect():
        if entrypoint == "api":
            return inspect_project(project_id, config=config)
        result = CliRunner().invoke(
            app, ["project", "show", project_id, "--config", str(config), "--json"]
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload.pop("command") == "project.show"
        return payload

    expected = inspect()
    assert expected["review"]["run_id"].startswith(f"projects/{project_id}/")
    assert expected["review"]["formats"] == ["md"]
    assert expected["guidance_inputs"]["state"] == "matches_inputs"
    changed = yaml.safe_load(config.read_text())
    changed["variants"]["default"] = "cover-letter"
    for key in ("projects", "runs", "sot"):
        changed["paths"][key] = f"../different/{key}"
    original_read = Path.read_bytes
    reads = []

    def mutate_after_read(path):
        content = original_read(path)
        if path == config:
            reads.append(path)
            if mutation == "edit":
                path.write_text(yaml.safe_dump(changed))
            else:
                path.unlink()
        return content

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", mutate_after_read)
        observed = inspect()
    assert observed == expected
    assert reads == [config]
    if mutation == "edit":
        refreshed = inspect_project(paths.project_dir, config=config)
        assert refreshed["review"]["run_id"] is None
        assert "default_variant" in refreshed["guidance_inputs"]["changed"]
    else:
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            inspect_project(paths.project_dir, config=config)


def test_project_inspection_reuses_an_explicit_snapshot(guided_project):
    config, paths = guided_project
    expected = inspect_project(paths.project_dir.name, config=config)
    preview = inspect_project_preview(paths.project_dir, config=config)
    snapshot = read_config(config)
    config.unlink()
    assert inspect_project(paths.project_dir.name, config=snapshot) == expected
    assert inspect_project_preview(paths.project_dir, config=snapshot) == preview


def test_project_inspection_is_read_only_and_terminal_independent(guided_project, capsys):
    config, paths = guided_project
    root = config.parent.parent
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    full = inspect_project(paths.project_dir, config=config)
    preview = inspect_project_preview(paths.project_dir, config=config)
    assert full["project"]["project_id"] == preview["project_id"]
    assert full["guidance_inputs"] == preview["guidance_inputs"]
    assert full["patch"]["status"] == preview["patch_status"]
    assert "job_artifacts" in full and "job_artifacts" not in preview
    assert "commands" not in preview and "review" not in preview
    assert capsys.readouterr() == ("", "")
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (None, "Config file not found"),
        (b"paths: [", "Config is invalid YAML"),
        (b"[]", "Config must be a YAML mapping"),
        (b"\xff", "Config must be UTF-8"),
    ],
)
def test_project_show_reports_configuration_errors(tmp_path, content, message):
    config = tmp_path / "workbench.yaml"
    if content is not None:
        config.write_bytes(content)
    result = CliRunner().invoke(
        app, ["project", "show", "research", "--config", str(config), "--json"]
    )
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.startswith(f"ERROR: {message}")
    assert isinstance(result.exception, SystemExit)
    assert set(tmp_path.iterdir()) == ({config} if content is not None else set())
