"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/workspace/projects/test_routing.py

Verify project selectors and suggested commands retain their workspace and target.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import json
import os
import shlex
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.ops.projects import ProjectError, guide_project, resolve_project_dir
from cvworkbench.ops.scaffold import init_project
from cvworkbench.ops.variant_lifecycle import list_variant_inbox, register_variant
from cvworkbench.workspace.projects import inspect_project
from cvworkbench.workspace.variants import inbox_entry_payload, inbox_summary_line


@pytest.fixture
def workspace(tmp_path):
    init_project(tmp_path, sample_default=True)
    config = tmp_path / "config/workbench.yaml"
    job = tmp_path / "job.txt"
    job.write_text("Research scientist with Python experience.\n")
    project = guide_project(
        config_path=config, job_file=job, variant_id="base", slug="research"
    ).paths
    return config, project


def _copy_project(config, project):
    copy = config.parent.parent / "var" / "archive" / "Saved project's $draft; literal"
    shutil.copytree(project.project_dir, copy)
    register_variant(
        variant_path=copy / "proposals/variant.yaml",
        cleanup_path=copy / "proposals",
        source="project",
        config_path=config,
        label="Saved project",
    )
    return copy


def _command_args(command):
    tokens = shlex.split(command)
    return tokens[tokens.index("cvw") + 1 :]


def test_project_ids_are_not_shadowed_by_the_working_directory(workspace, monkeypatch):
    config, project = workspace
    caller = config.parent.parent / "caller"
    shadow = caller / "research"
    shutil.copytree(project.project_dir, shadow)
    monkeypatch.chdir(caller)
    assert resolve_project_dir("research", config).resolve() == project.project_dir
    assert resolve_project_dir("./research", config).resolve() == shadow
    assert resolve_project_dir(Path("research"), config).resolve() == shadow
    assert inspect_project("research", config=config)["project"]["project_dir"] == str(
        project.project_dir
    )
    assert inspect_project(Path("research"), config=config)["project"]["project_dir"] == str(shadow)


def test_missing_explicit_path_does_not_resolve_under_the_project_store(workspace, monkeypatch):
    config, project = workspace
    caller = config.parent.parent / "caller"
    caller.mkdir()
    shutil.copytree(project.project_dir, project.project_dir.parent / "nested/research")
    monkeypatch.chdir(caller)
    assert resolve_project_dir("nested/research", config).resolve() == caller / "nested/research"
    with pytest.raises(ProjectError, match="Project directory not found"):
        inspect_project("nested/research", config=config)


def test_commands_preserve_an_explicit_project_directory(workspace):
    config, project = workspace
    copied = _copy_project(config, project)
    summary = inspect_project(copied, config=config)
    for name, command in summary["commands"].items():
        args = _command_args(command)
        selector = args[2] if name in {"show", "apply"} else args[args.index("--project") + 1]
        assert selector == str(copied), (name, command)
        assert args[args.index("--config") + 1] == str(config)
    result = CliRunner().invoke(app, [*_command_args(summary["commands"]["show"]), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["project"]["project_dir"] == str(copied)


def test_suggested_discard_does_not_delete_a_same_id_neighbor(workspace):
    config, project = workspace
    copied = _copy_project(config, project)
    before = project.variant_path.read_bytes()
    command = inspect_project(copied, config=config)["commands"]["discard"]
    result = CliRunner().invoke(app, _command_args(command))
    assert result.exit_code == 0, result.output
    assert project.variant_path.is_file(), "The suggested command deleted the other proposal"
    assert project.variant_path.read_bytes() == before
    assert not (copied / "proposals").exists()
    assert (copied / "project.yaml").is_file()


@pytest.mark.parametrize("command", ["new", "guide"])
def test_plain_creation_suggestions_keep_the_configuration(workspace, monkeypatch, command):
    config, _ = workspace
    caller = config.parent.parent / "caller"
    caller.mkdir()
    monkeypatch.chdir(caller)
    result = CliRunner().invoke(
        app,
        [
            "project",
            command,
            "--job-file",
            str(config.parent.parent / "job.txt"),
            "--slug",
            "second",
            "--config",
            str(config),
            "--plain",
        ],
    )
    assert result.exit_code == 0, result.output
    next_step = next(
        line.split(": ", 1)[1]
        for line in result.stdout.splitlines()
        if line.startswith("next_step: ")
    )
    args = _command_args(next_step)
    assert "--config" in args, next_step
    assert args[args.index("--config") + 1] == str(config)
    shown = CliRunner().invoke(app, [*args, "--json"])
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.stdout)["project"]["project_id"] == "second"


@pytest.mark.parametrize("layout", ["archive", "configured_store"])
def test_inbox_commands_use_the_registered_project_location(workspace, layout):
    config, project = workspace
    if layout == "archive":
        target = _copy_project(config, project)
    else:
        data = yaml.safe_load(config.read_text())
        data["paths"]["projects"] = "../var/campaigns"
        config.write_text(yaml.safe_dump(data))
        target = guide_project(
            config_path=config,
            job_file=config.parent.parent / "job.txt",
            variant_id="base",
            slug="research",
        ).paths.project_dir
    entry = next(
        item
        for item in list_variant_inbox(config)
        if item.variant_path == target / "proposals/variant.yaml"
    )
    payload = inbox_entry_payload(entry, config)
    assert payload["selector_kind"] == "project"
    assert payload["project_id"] == "research"
    expected = str(target) if layout == "archive" else "research"
    assert payload["selector"] == expected
    for key in ("keep_command", "discard_command", "preview_command"):
        args = _command_args(payload[key])
        assert args[args.index("--project") + 1] == expected


def test_inbox_reports_invalid_project_identity_without_guessing_a_selector(workspace):
    config, project = workspace
    (project.project_dir / "project.yaml").write_text("project:\n  id: [research]\n")
    entry = next(item for item in list_variant_inbox(config) if item.source == "project")
    payload = inbox_entry_payload(entry, config)
    assert payload["selector_kind"] == "path"
    assert payload["project_id"] is None
    assert payload["selector"] == str(project.variant_path)
    assert payload["project_error"].startswith("Project id must")
    assert "preview_command" not in payload
    assert payload["project_error"] in inbox_summary_line([payload])
    for key in ("keep_command", "discard_command"):
        args = _command_args(payload[key])
        assert "--project" not in args
        assert args[args.index("--path") + 1] == str(project.variant_path)
    result = CliRunner().invoke(app, ["variant", "inbox", "--config", str(config), "--plain"])
    assert result.exit_code == 0, result.output
    assert payload["project_error"] in result.stdout


@pytest.mark.parametrize("kind", ["external_symlink", "fifo"])
def test_inbox_does_not_open_a_manifest_outside_its_project_or_a_named_pipe(
    workspace, monkeypatch, kind
):
    config, project = workspace
    entry = next(item for item in list_variant_inbox(config) if item.source == "project")
    manifest = project.project_dir / "project.yaml"
    outside = config.parent.parent / "outside.yaml"
    outside.write_bytes(manifest.read_bytes())
    manifest.unlink()
    if kind == "external_symlink":
        manifest.symlink_to(outside)
    else:
        os.mkfifo(manifest)
    original_open = Path.open
    reads = []

    def observe_open(path, *args, **kwargs):
        if path.resolve() in (manifest, outside):
            reads.append(path)
            if kind == "fifo":
                raise AssertionError("Inbox must not open a named pipe")
        return original_open(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", observe_open)
        payload = inbox_entry_payload(entry, config)
    assert reads == []
    assert payload["selector_kind"] == "path"
    assert payload["project_id"] is None
    assert "project_error" in payload
    assert "preview_command" not in payload


@pytest.mark.parametrize("selector", ["", "invalid id"])
@pytest.mark.parametrize(
    "command",
    [
        ["project", "show"],
        ["project", "apply"],
        ["build"],
        ["preview"],
        ["variant", "keep"],
        ["variant", "discard"],
        ["reviewpack"],
    ],
)
def test_cli_project_selector_errors_are_explicit_and_write_nothing(workspace, selector, command):
    config, _ = workspace
    root = config.parent.parent
    before = {p.relative_to(root): p.read_bytes() if p.is_file() else None for p in root.rglob("*")}
    selection = [selector] if command[0] == "project" else ["--project", selector]
    options = []
    if command == ["preview"]:
        options = ["--once"]
    elif command == ["build"]:
        options = ["--format", "md"]
    result = CliRunner().invoke(
        app, [*command, *selection, *options, "--config", str(config), "--json"]
    )
    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    message = "Project selector is required" if not selector else "Project id must"
    assert result.stderr.startswith(f"ERROR: {message}")
    assert isinstance(result.exception, SystemExit)
    assert before == {
        p.relative_to(root): p.read_bytes() if p.is_file() else None for p in root.rglob("*")
    }
