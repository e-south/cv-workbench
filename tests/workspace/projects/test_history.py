"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/workspace/projects/test_history.py

Verify retained project inspection independently of executable proposal inputs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import json
import os
import shlex
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.ops.projects import ProjectError, guide_project, load_project, load_project_details
from cvworkbench.ops.scaffold import init_project
from cvworkbench.workspace.projects import inspect_project, inspect_project_preview


@pytest.fixture
def project(tmp_path):
    init_project(tmp_path, sample_default=True)
    config = tmp_path / "config/workbench.yaml"
    job = tmp_path / "job.txt"
    job.write_text("Research scientist with Python experience.\n")
    paths = guide_project(
        config_path=config, job_file=job, variant_id="base", slug="research"
    ).paths
    return config, paths


def _tree(root):
    return {p.relative_to(root): p.read_bytes() if p.is_file() else None for p in root.rglob("*")}


@pytest.mark.parametrize("artifact", ["variant", "patch"])
@pytest.mark.parametrize(
    ("failure", "state"),
    [
        ("missing", "missing"),
        ("yaml", "invalid"),
        ("utf8", "invalid"),
        ("schema", "invalid"),
        ("directory", "unreadable"),
    ],
)
def test_unavailable_proposal_preserves_project_history(project, artifact, failure, state):
    config, paths = project
    path = paths.variant_path if artifact == "variant" else paths.patch_path
    if failure == "missing":
        path.unlink()
    elif failure == "yaml":
        path.write_text("invalid: [private-fixture-marker\n")
    elif failure == "utf8":
        path.write_bytes(b"\xff")
    elif failure == "schema":
        path.write_text(
            "patch:\n  format: unified-diff\n  diff: private-fixture-marker\n"
            if artifact == "patch"
            else "private-fixture-marker: true\n"
        )
    else:
        path.unlink()
        path.mkdir()
    before = _tree(config.parent.parent)

    details = load_project_details(paths.project_dir)
    assert details.proposal_available is False
    assert [(issue.artifact, issue.state) for issue in details.proposal_issues] == [
        (artifact, state)
    ]
    full = inspect_project(paths.project_dir, config=config)
    preview = inspect_project_preview(paths.project_dir, config=config)
    assert full["project"]["project_id"] == "research"
    assert full["job_artifact_status"] == "match saved record"
    assert full["proposal_plan"]["applied_variant"] == "base"
    assert full["guidance_inputs"]["state"] == "matches_inputs"
    assert full["proposal"]["status"] == "unavailable"
    assert full["proposal"]["issues"][0]["state"] == state
    assert set(full["commands"]) == {"show"}
    assert full["review"]["next_command"] is None
    assert "project_context_error" not in preview
    assert preview["proposal_status"] == "unavailable"
    assert artifact in preview["proposal_warning"]
    if artifact == "patch":
        assert full["patch"]["status"] == "unavailable"
        for field in ("format", "is_empty", "line_count", "operations"):
            assert full["patch"][field] is None
    else:
        assert full["proposal"]["variant_id"] is None
        assert full["proposal"]["document_type"] is None
        assert full["patch"]["status"] == "empty"
    assert "private-fixture-marker" not in json.dumps(full)
    for mode in ("--json", "--plain"):
        shown = CliRunner().invoke(
            app, ["project", "show", "research", "--config", str(config), mode]
        )
        assert shown.exit_code == 0, shown.output
        assert shown.stderr == ""
        if mode == "--json":
            assert json.loads(shown.stdout) == {"command": "project.show", **full}
        else:
            assert "unavailable" in shown.stdout and artifact in shown.stdout
            assert "build_step" not in shown.stdout
    assert _tree(config.parent.parent) == before


@pytest.mark.parametrize("artifact", ["variant", "patch"])
@pytest.mark.parametrize("failure", ["external_symlink", "fifo"])
def test_proposal_inspection_checks_ownership_and_file_kind_before_read(
    project, monkeypatch, artifact, failure
):
    config, paths = project
    path = paths.variant_path if artifact == "variant" else paths.patch_path
    outside = config.parent.parent / "outside.yaml"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    if failure == "external_symlink":
        path.symlink_to(outside)
    else:
        os.mkfifo(path)
    original_open = Path.open
    reads = []

    def observe_open(candidate, *args, **kwargs):
        if candidate.resolve() in (path, outside):
            reads.append(candidate)
            if failure == "fifo":
                raise AssertionError("Inspection must not open a named pipe")
        return original_open(candidate, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", observe_open)
        full = inspect_project(paths.project_dir, config=config)
    assert reads == []
    assert full["proposal"]["status"] == "unavailable"
    assert full["proposal"]["issues"][0]["state"] == "unreadable"
    assert "proposal_plan" in full


def test_discarded_proposal_retains_a_runnable_pinned_review_command(project):
    config, paths = project
    runner = CliRunner()
    build = runner.invoke(
        app,
        [
            "build",
            "--project",
            "research",
            "--config",
            str(config),
            "--format",
            "md,pdf,docx",
            "--json",
        ],
    )
    assert build.exit_code == 0, build.output
    retained = inspect_project("research", config=config)["review"]["run_id"]
    discard = runner.invoke(
        app,
        ["variant", "discard", "--project", "research", "--config", str(config), "--yes", "--json"],
    )
    assert discard.exit_code == 0, discard.output
    before = _tree(config.parent.parent)

    full = inspect_project("research", config=config)
    assert full["proposal"]["status"] == "unavailable"
    assert {issue["artifact"] for issue in full["proposal"]["issues"]} == {"variant", "patch"}
    assert full["review"]["review_ready"] is True
    assert full["review"]["run_id"] == retained
    assert set(full["commands"]) == {"show", "reviewpack"}
    assert full["review"]["next_command"] == full["commands"]["reviewpack"]
    assert _tree(config.parent.parent) == before
    with pytest.raises(ProjectError, match="Project variant not found"):
        load_project(paths.project_dir)
    for command in ("build", "project apply"):
        args = shlex.split(command)
        args += (
            ["research"]
            if command == "project apply"
            else ["--project", "research", "--format", "md"]
        )
        failed = runner.invoke(app, [*args, "--config", str(config)])
        assert failed.exit_code == 1, failed.output
        assert "Project variant not found" in failed.stderr
        assert _tree(config.parent.parent) == before
    review = shlex.split(full["commands"]["reviewpack"])
    result = runner.invoke(app, review[review.index("reviewpack") :])
    assert result.exit_code == 0, result.output
    assert retained in result.stdout


@pytest.mark.parametrize("selector", ["project", "run"])
def test_review_pack_requires_retained_run_inputs_without_live_proposals(project, selector):
    from cvworkbench.ops.review.packs import build_review_pack
    from cvworkbench.ops.review.record import load_source_record, validate_source_artifacts

    config, paths = project
    result = CliRunner().invoke(
        app,
        [
            "build",
            "--project",
            "research",
            "--config",
            str(config),
            "--format",
            "md,pdf,docx",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    run_id = inspect_project("research", config=config)["review"]["run_id"]
    paths.variant_path.unlink()
    paths.patch_path.unlink()
    (config.parent / "variants/base.yaml").unlink()
    source = config.parent.parent / "sot.sample"
    source.rename(source.with_name("retained-source"))
    pack = build_review_pack(
        config_path=config,
        variant_id=None,
        run=run_id if selector == "run" else None,
        project_dir=paths.project_dir if selector == "project" else None,
    )
    assert pack.run_id == run_id
    assert pack.out_dir == config.parent.parent / "var/reviews/projects/research"
    record = load_source_record(pack.source_record_path)
    validate_source_artifacts(record)
    docx_source = next(name for name in record.files if Path(name).name == record.docx_name)
    assert pack.docx_path.read_bytes() == (Path(record.run_path) / docx_source).read_bytes()
    before_import = _tree(config.parent.parent)
    imported = CliRunner().invoke(
        app, ["import-docx", "--from", str(pack.docx_path), "--config", str(config), "--json"]
    )
    assert imported.exit_code == 1, imported.output
    assert "Project variant not found" in imported.stderr
    assert _tree(config.parent.parent) == before_import


def test_import_target_rejects_changed_project_identity(project):
    from cvworkbench.ops.review import ReviewError
    from cvworkbench.ops.review.targets import resolve_review_target

    config, paths = project
    result = CliRunner().invoke(
        app, ["build", "--project", "research", "--config", str(config), "--format", "md", "--json"]
    )
    assert result.exit_code == 0, result.output
    run_id = inspect_project("research", config=config)["review"]["run_id"]
    manifest = yaml.safe_load(paths.project_file.read_text())
    manifest["project"]["id"] = "different"
    paths.project_file.write_text(yaml.safe_dump(manifest))
    before = _tree(config.parent.parent)

    with pytest.raises(ReviewError, match="Project identity does not match selected run"):
        resolve_review_target(config_path=config, run=run_id, variant_id=None, project_dir=None)
    assert _tree(config.parent.parent) == before
