"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/workspace/test_project_guidance.py

Verifies saved guidance diagnostics across project inspection and preview.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.dev.preview import _load_project_context
from cvworkbench.ops.projects import guide_project, retarget_project_variant
from cvworkbench.ops.scaffold import init_project


def _guided_project(root: Path):
    init_project(root, sample_default=True)
    config = root / "config/workbench.yaml"
    (config.parent / "variants/focus.yaml").write_text(
        "variant:\n  id: focus\n  outputs: [md]\n  include_tags: [leadership]\n"
    )
    job = root / "job.txt"
    job.write_text("Research scientist with Python experience.\n")
    result = guide_project(config_path=config, job_file=job, variant_id="base")
    return config, result.paths


def _show(config: Path, project_dir: Path):
    result = CliRunner().invoke(
        app, ["project", "show", str(project_dir), "--config", str(config), "--json"]
    )
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    return json.loads(result.stdout)


def test_retarget_surfaces_saved_guidance_selection_mismatch_without_rewriting_history(tmp_path):
    config, project = _guided_project(tmp_path)
    plan = project.job_dir / "proposal-plan.json"
    original = plan.read_bytes()
    assert "proposal_plan_warning" not in _show(config, project.project_dir)
    assert "proposal_plan_warning" not in _load_project_context(project.project_dir)

    retarget_project_variant(
        project_dir=project.project_dir, base_variant_id="focus", config_path=config
    )

    shown = _show(config, project.project_dir)
    preview = _load_project_context(project.project_dir)
    warning = shown["proposal_plan_warning"]
    assert "base" in warning and "focus" in warning
    assert "recorded" in warning
    assert preview["proposal_plan_warning"] == warning
    plain = CliRunner().invoke(
        app, ["project", "show", str(project.project_dir), "--config", str(config), "--plain"]
    )
    assert plain.exit_code == 0, plain.output
    assert "proposal_plan_warning" in plain.stdout
    assert plan.read_bytes() == original


@pytest.mark.parametrize("recorded", [None, False, "../private-fixture-marker"])
def test_guidance_reports_unverifiable_selection_without_echo(tmp_path, recorded):
    config, project = _guided_project(tmp_path)
    plan = project.job_dir / "proposal-plan.json"
    payload = json.loads(plan.read_text())
    payload["applied_variant"] = recorded
    plan.write_text(json.dumps(payload))

    shown = _show(config, project.project_dir)
    preview = _load_project_context(project.project_dir)

    assert "does not identify" in shown["proposal_plan_warning"]
    assert "private-fixture-marker" not in shown["proposal_plan_warning"]
    assert preview["proposal_plan_warning"] == shown["proposal_plan_warning"]


@pytest.mark.parametrize("invalid", ["json", "utf8", "directory"])
def test_optional_guidance_read_errors_preserve_inspection_and_preview(tmp_path, invalid):
    config, project = _guided_project(tmp_path)
    plan = project.job_dir / "proposal-plan.json"
    if invalid == "json":
        plan.write_text("{invalid private-fixture-marker")
    elif invalid == "utf8":
        plan.write_bytes(b"\xff")
    else:
        plan.unlink()
        plan.mkdir()

    shown = _show(config, project.project_dir)
    preview = _load_project_context(project.project_dir)

    assert shown["project"]["base_variant"] == "base"
    assert "private-fixture-marker" not in shown["proposal_plan_error"]
    assert str(plan) in shown["proposal_plan_error"]
    assert preview["proposal_plan_error"] == shown["proposal_plan_error"]


@pytest.mark.parametrize("consumer", ["show", "preview"])
def test_saved_guidance_rejects_external_symlink_before_read(tmp_path, monkeypatch, consumer):
    config, project = _guided_project(tmp_path)
    outside = tmp_path / "outside-plan.json"
    outside.write_text(json.dumps({"summary": "external-private-fixture-marker"}))
    original = outside.read_bytes()
    plan = project.job_dir / "proposal-plan.json"
    plan.unlink()
    plan.symlink_to(outside)
    outside_reads = []
    original_read = Path.read_text

    def observe_read(path, *args, **kwargs):
        if path.resolve() == outside:
            outside_reads.append(path)
        return original_read(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", observe_read)
        payload = (
            _show(config, project.project_dir)
            if consumer == "show"
            else _load_project_context(project.project_dir)
        )

    assert outside_reads == []
    assert "proposal_plan_error" in payload
    assert "within the project directory" in payload["proposal_plan_error"]
    assert "external-private-fixture-marker" not in json.dumps(payload)
    assert outside.read_bytes() == original
    assert plan.is_symlink()


def test_saved_guidance_accepts_internal_symlink(tmp_path):
    config, project = _guided_project(tmp_path)
    plan = project.job_dir / "proposal-plan.json"
    retained = project.job_dir / "retained-plan.json"
    plan.rename(retained)
    plan.symlink_to(retained)

    shown = _show(config, project.project_dir)
    preview = _load_project_context(project.project_dir)

    assert "proposal_plan_error" not in shown
    assert "proposal_plan_error" not in preview
    assert shown["proposal_plan"]["summary"] == preview["recommendation_summary"]
