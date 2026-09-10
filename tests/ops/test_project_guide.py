"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_project_guide.py

Tests reusable project guidance, input preflight, and failed-workspace recovery.

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
from cvworkbench.ops.projects import load_project
from cvworkbench.ops.scaffold import init_project
from cvworkbench.ops.variant_lifecycle import list_variant_inbox


def _workspace(root: Path) -> tuple[Path, Path, Path]:
    init_project(root, sample_default=True)
    config = root / "config/workbench.yaml"
    source = root / "sot.sample"
    experience = source / "experience.yaml"
    data = yaml.safe_load(experience.read_text())
    data["roles"][0]["bullets"][0]["tags"] = ["reliability", "leadership"]
    experience.write_text(yaml.safe_dump(data))
    for name, rule in [
        ("ops", "include_tags: [reliability]"),
        ("cover", "include_tags: [leadership]"),
    ]:
        (config.parent / f"variants/{name}.yaml").write_text(
            f"variant:\n  id: {name}\n  outputs: [md]\n  {rule}\n"
        )
    job = root / "job.txt"
    job.write_text("Reliability reliability reliability and leadership.\n")
    return config, source, job


def _tree(root: Path) -> dict[Path, bytes | None]:
    return {
        path.relative_to(root): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


@pytest.mark.parametrize(
    "variant_id,applied,mode", [(None, "ops", "recommended"), ("cover", "cover", "explicit")]
)
def test_guidance_api_selects_and_records_a_project_without_terminal_output(
    tmp_path: Path, capsys, variant_id: str | None, applied: str, mode: str
) -> None:
    from cvworkbench.ops.projects import guide_project

    config, source, job = _workspace(tmp_path)
    source_before = _tree(source)

    result = guide_project(config_path=config, job_file=job, variant_id=variant_id)

    assert result.applied_variant_id == applied
    assert result.default_variant_id == "base"
    assert result.proposal_variant_id == "proposal-job"
    assert result.recommendations[0]["variant_id"] == "ops"
    assert result.proposal_plan["selection_mode"] == mode
    assert result.proposal_plan["applied_variant"] == applied
    assert (
        json.loads((result.paths.job_dir / "proposal-plan.json").read_text())
        == result.proposal_plan
    )
    assert load_project(result.paths.project_dir).base_variant_id == applied
    assert len(list_variant_inbox(config)) == 1
    assert _tree(source) == source_before
    output = capsys.readouterr()
    assert output.out == output.err == ""


def test_guide_preflights_variant_catalog_before_creating_a_project(tmp_path: Path) -> None:
    config, _, job = _workspace(tmp_path)
    (config.parent / "variants/broken.yaml").write_text(
        "variant:\n  id: broken\n  outputs: invalid\n"
    )
    before = _tree(tmp_path)

    result = CliRunner().invoke(
        app, ["project", "guide", "--job-file", str(job), "--config", str(config), "--json"]
    )

    assert result.exit_code == 1
    assert "outputs" in result.stderr
    assert "Traceback" not in result.output
    assert _tree(tmp_path) == before


def test_guidance_api_reports_all_source_errors_before_writes(tmp_path: Path, capsys) -> None:
    from cvworkbench.ops.projects import ProjectGuideError, guide_project

    config, source, job = _workspace(tmp_path)
    (source / "person.yaml").unlink()
    (source / "letters.yaml").unlink()
    before = _tree(tmp_path)

    with pytest.raises(ProjectGuideError) as caught:
        guide_project(config_path=config, job_file=job)

    assert caught.value.errors == (
        "Missing required file: person.yaml",
        "Missing required file: letters.yaml",
    )
    assert _tree(tmp_path) == before
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.parametrize(
    "job_url,with_file", [(None, False), ("https://example.invalid/job", True), ("", True)]
)
def test_guidance_api_requires_exactly_one_job_source(
    tmp_path: Path, job_url: str | None, with_file: bool
) -> None:
    from cvworkbench.ops.projects import ProjectGuideError, guide_project

    with pytest.raises(ProjectGuideError, match="exactly one"):
        guide_project(
            config_path=tmp_path / "missing.yaml",
            job_url=job_url,
            job_file=tmp_path / "job.txt" if with_file else None,
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("job_url", ["", " "])
def test_guidance_rejects_blank_url_before_other_inputs(tmp_path: Path, job_url: str) -> None:
    from cvworkbench.ops.projects import ProjectGuideError, guide_project

    with pytest.raises(ProjectGuideError, match="Job URL is required"):
        guide_project(config_path=tmp_path / "missing.yaml", job_url=job_url)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("variant_id", ["", False, 0])
def test_guidance_rejects_invalid_explicit_variant_without_using_default(
    tmp_path: Path, variant_id: object
) -> None:
    from cvworkbench.ops.projects import ProjectGuideError, guide_project

    config, _, job = _workspace(tmp_path)
    before = _tree(tmp_path)

    with pytest.raises(ProjectGuideError, match="Variant id"):
        guide_project(config_path=config, job_file=job, variant_id=variant_id)

    assert _tree(tmp_path) == before


def test_guidance_reports_invalid_url_registry_settings_without_writes(tmp_path: Path) -> None:
    from cvworkbench.ops.projects import ProjectGuideError, guide_project

    config, _, _ = _workspace(tmp_path)
    data = yaml.safe_load(config.read_text())
    data["registry"] = {"user_agent": 42}
    config.write_text(yaml.safe_dump(data))
    before = _tree(tmp_path)

    with pytest.raises(ProjectGuideError, match="registry.user_agent"):
        guide_project(config_path=config, job_url="https://localhost/job")
    result = CliRunner().invoke(
        app, ["project", "guide", "--job-url", "https://localhost/job", "--config", str(config)]
    )
    assert result.exit_code == 1
    assert "registry.user_agent" in result.stderr
    assert "Traceback" not in result.output
    assert _tree(tmp_path) == before


def test_guidance_plan_write_failure_removes_project_and_active_proposal(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from cvworkbench.ops.projects import ProjectGuideError, guide_project

    config, source, job = _workspace(tmp_path)
    snapshot = read_config(config)
    source_before = _tree(source)
    original_write = Path.write_text

    def obstruct_plan(path, data, *args, **kwargs):
        if path.name == "proposal-plan.json":
            config.unlink()
            path.mkdir()
        return original_write(path, data, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "write_text", obstruct_plan)
        with pytest.raises(ProjectGuideError, match="proposal-plan.json"):
            guide_project(config_path=config, job_file=job)

    assert not (tmp_path / "var/projects/job").exists()
    assert list_variant_inbox(snapshot) == []
    assert _tree(source) == source_before
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.parametrize("mutation", ["edit", "remove"])
def test_guidance_uses_one_configuration_generation(
    tmp_path: Path, monkeypatch, mutation: str
) -> None:
    from cvworkbench.ops.projects import guide_project

    config, source, job = _workspace(tmp_path)
    snapshot = read_config(config)
    changed = yaml.safe_load(config.read_text())
    changed["paths"]["projects"] = "../different/projects"
    changed["variants"]["default"] = "cover"
    original_read = Path.read_bytes
    reads = []

    def replace_after_read(path):
        content = original_read(path)
        if path == config:
            reads.append(path)
            if mutation == "edit":
                path.write_text(yaml.safe_dump(changed))
            else:
                path.unlink()
        return content

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", replace_after_read)
        result = guide_project(config_path=config, job_file=job)

    assert result.config_path == config
    assert result.sot_path == source
    assert result.default_variant_id == "base"
    assert result.paths.project_dir == tmp_path / "var/projects/job"
    assert result.applied_variant_id == "ops"
    assert not (tmp_path / "different").exists()
    assert len(list_variant_inbox(snapshot)) == 1
    assert reads == [config]


def test_guidance_accepts_an_explicit_configuration_snapshot(tmp_path: Path) -> None:
    from cvworkbench.ops.projects import guide_project

    config, _, job = _workspace(tmp_path)
    snapshot = read_config(config)
    config.unlink()

    result = guide_project(config_path=snapshot, job_file=job)

    assert result.paths.project_dir == tmp_path / "var/projects/job"
    assert len(list_variant_inbox(snapshot)) == 1


@pytest.mark.parametrize("failure", ["missing_variant", "job_directory"])
def test_guidance_rejects_unusable_inputs_before_creating_directories(
    tmp_path: Path, monkeypatch, failure: str
) -> None:
    from cvworkbench.ops.projects import ProjectGuideError, guide_project

    config, _, job = _workspace(tmp_path)
    if failure == "job_directory":
        job.unlink()
        job.mkdir()
    before = _tree(tmp_path)
    created = []
    original_mkdir = Path.mkdir

    def observe_mkdir(path, *args, **kwargs):
        absent = not path.exists()
        result = original_mkdir(path, *args, **kwargs)
        if absent:
            created.append(path)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(Path, "mkdir", observe_mkdir)
        with pytest.raises(ProjectGuideError):
            guide_project(
                config_path=config,
                job_file=job,
                variant_id="missing" if failure == "missing_variant" else None,
            )

    assert _tree(tmp_path) == before
    assert created == []


def test_guidance_cancellation_preserves_interrupt_and_discards_partial_project(
    tmp_path: Path, monkeypatch
) -> None:
    from cvworkbench.ops.projects import guide_project

    config, source, job = _workspace(tmp_path)
    source_before = _tree(source)
    original_write = Path.write_text

    def interrupt_plan(path, data, *args, **kwargs):
        if path.name == "proposal-plan.json":
            raise KeyboardInterrupt("guidance cancelled")
        return original_write(path, data, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "write_text", interrupt_plan)
        with pytest.raises(KeyboardInterrupt, match="guidance cancelled"):
            guide_project(config_path=config, job_file=job)

    assert not (tmp_path / "var/projects/job").exists()
    assert list_variant_inbox(config) == []
    assert _tree(source) == source_before
