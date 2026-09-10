"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_project_build.py

Verify project builds validate inputs before allocating persistent artifacts.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import hashlib
import json

import pytest
import yaml
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.config import read_config
from cvworkbench.ops import projects
from cvworkbench.ops.scaffold import init_project


@pytest.fixture
def project(tmp_path):
    init_project(tmp_path, sample_default=True)
    config = tmp_path / "config/workbench.yaml"
    source = tmp_path / "sot.sample"
    (source / "projects.yaml").write_text(
        "projects:\n  - id: study\n    name: Study\n    summary: Original summary.\n    tags: [core]\n"
    )
    job = tmp_path / "job.txt"
    job.write_text("Research scientist with Python experience.\n")
    paths = projects.guide_project(
        config_path=config, job_file=job, variant_id="base", slug="research"
    ).paths
    projects.append_replace_project_summary_operation(
        project_dir=paths.project_dir,
        sot_path=source,
        project_id="study",
        new_text="Tailored summary.",
    )
    return config, source, paths


def _tree(root):
    return {
        path.relative_to(root): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


@pytest.mark.parametrize(
    "failure",
    ["theme", "preset", "formats", "empty_formats", "source", "variant", "patch", "letter"],
)
def test_cli_project_build_rejects_invalid_inputs_without_persistent_writes(project, failure):
    config, source, paths = project
    options = ["--format", "md"]
    if failure == "theme":
        options += ["--theme", "missing-theme"]
        expected = "Theme not found"
    elif failure == "preset":
        options = ["--format", "html", "--style-preset", "missing-preset"]
        expected = "not found"
    elif failure == "formats":
        options = ["--format", "unknown"]
        expected = "Unsupported output format"
    elif failure == "empty_formats":
        options = ["--format", " "]
        expected = "No output formats selected"
    elif failure == "source":
        (source / "education.yaml").write_text("education: wrong-type\n")
        expected = "education"
    elif failure == "variant":
        variant = yaml.safe_load(paths.variant_path.read_text())
        variant["variant"]["id"] = "../outside"
        paths.variant_path.write_text(yaml.safe_dump(variant))
        expected = "Variant id"
    elif failure == "letter":
        variant = yaml.safe_load(paths.variant_path.read_text())
        variant["variant"].update(document_type="cover-letter", letter_id="missing-letter")
        paths.variant_path.write_text(yaml.safe_dump(variant))
        expected = "Letter not found"
    else:
        patch = yaml.safe_load(paths.patch_path.read_text())
        patch["patch"]["operations"][0]["old_text"] = "Unmatched original text."
        paths.patch_path.write_text(yaml.safe_dump(patch))
        expected = "source text mismatch"
    root = config.parent.parent
    before = _tree(root)
    result = CliRunner().invoke(
        app,
        ["build", "--project", "research", "--config", str(config), *options, "--json"],
    )
    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert expected in result.stderr
    assert _tree(root) == before


def test_project_build_api_retains_tailored_source_and_auditable_outputs(project, capsys):
    config, source, paths = project
    before_source = _tree(source)
    before_project = _tree(paths.project_dir)
    result = projects.build_project("research", config_path=config, formats=["md", "html"])
    assert result.run_dir.parent == config.parent.parent / "var/runs/projects/research"
    assert result.dist_dir == result.run_dir
    assert "Tailored summary." in (result.run_dir / "cv.md").read_text()
    retained = result.run_dir / "sot/projects.yaml"
    assert yaml.safe_load(retained.read_text())["projects"][0]["summary"] == "Tailored summary."
    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    assert (
        manifest["sot_hashes"]["projects.yaml"] == hashlib.sha256(retained.read_bytes()).hexdigest()
    )
    assert _tree(source) == before_source
    assert _tree(paths.project_dir) == before_project
    assert not (config.parent.parent / "var/dist" / result.variant.id).exists()
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("change", ["edit", "remove", "captured"])
def test_project_build_uses_one_configuration_generation(project, monkeypatch, change):
    from cvworkbench.ops.projects import building

    config, _, _ = project
    initial = config.read_bytes()
    snapshot = read_config(config)
    original_prepare = building.prepare_project_sot

    def prepare_and_change_settings(**kwargs):
        prepared = original_prepare(**kwargs)
        if change == "edit":
            data = yaml.safe_load(initial)
            data["paths"]["runs"] = "../escaped-runs"
            data["render"]["theme"] = "absent-theme"
            config.write_text(yaml.safe_dump(data))
        elif change == "remove":
            config.unlink()
        return prepared

    monkeypatch.setattr(building, "prepare_project_sot", prepare_and_change_settings)
    if change == "captured":
        config.unlink()
    result = projects.build_project(
        "research", config_path=snapshot if change == "captured" else config, formats=["md"]
    )
    assert result.theme_id == "default"
    assert result.run_dir.parent == config.parent.parent / "var/runs/projects/research"
    assert not (config.parent.parent / "escaped-runs").exists()
    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    assert manifest["configuration"]["sha256"] == hashlib.sha256(initial).hexdigest()


def test_project_build_reports_each_source_validation_error_before_writing(project):
    config, source, _ = project
    (source / "education.yaml").unlink()
    (source / "skills.yaml").unlink()
    before = _tree(config.parent.parent)
    with pytest.raises(projects.ProjectBuildError) as caught:
        projects.build_project("research", config_path=config, formats=["md"])
    assert caught.value.errors == (
        "Missing required file: skills.yaml",
        "Missing required file: education.yaml",
    )
    cli = CliRunner().invoke(
        app, ["build", "--project", "research", "--config", str(config), "--format", "md", "--json"]
    )
    assert cli.exit_code == 1
    assert cli.stdout == ""
    assert cli.stderr == "".join(f"ERROR: {error}\n" for error in caught.value.errors)
    assert _tree(config.parent.parent) == before
