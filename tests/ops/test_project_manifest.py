"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_project_manifest.py

Tests project identity validation before artifact selection and workspace inspection.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.ops.projects import (
    ProjectError,
    create_project_from_file,
    load_project,
    load_project_details,
)
from cvworkbench.ops.scaffold import init_project
from cvworkbench.workspace.projects import load_project_summaries


def _project(root: Path) -> tuple[Path, Path]:
    init_project(root, sample_default=True)
    config = root / "config/workbench.yaml"
    job = root / "job.txt"
    job.write_text("Research scientist with Python experience.\n")
    paths = create_project_from_file(
        job_path=job,
        slug="research",
        base_variant_id="base",
        config_path=config,
        sot_path=root / "sot.sample",
        store_raw=False,
    )
    return config, paths.project_dir


def _tree(root: Path) -> dict[Path, bytes | None]:
    return {
        path.relative_to(root): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


@pytest.mark.parametrize("field", ["id", "base_variant"])
@pytest.mark.parametrize(
    "value", [None, True, 42, [], {}, "", "..", "../outside", "job/child", "job --help"]
)
def test_project_manifest_rejects_invalid_identifiers_in_load_and_inventory(
    tmp_path: Path, field: str, value: object
) -> None:
    config, project_dir = _project(tmp_path)
    manifest = project_dir / "project.yaml"
    data = yaml.safe_load(manifest.read_text())
    data["project"][field] = value
    manifest.write_text(yaml.safe_dump(data))
    before = _tree(tmp_path)

    with pytest.raises(ProjectError, match=f"Project {field}"):
        load_project(project_dir)
    summaries, invalid = load_project_summaries(config)
    assert summaries == []
    assert invalid == [project_dir]
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("absolute", [False, True])
def test_project_build_rejects_manifest_id_before_writes(tmp_path: Path, absolute: bool) -> None:
    config, project_dir = _project(tmp_path)
    manifest = project_dir / "project.yaml"
    data = yaml.safe_load(manifest.read_text())
    data["project"]["id"] = str(tmp_path / "outside-runs") if absolute else "../../outside-runs"
    manifest.write_text(yaml.safe_dump(data))
    before = _tree(tmp_path)

    result = CliRunner().invoke(
        app, ["build", "--project", str(project_dir), "--format", "md", "--config", str(config)]
    )

    assert result.exit_code == 1, result.output
    assert "Project id" in result.stderr
    assert "Traceback" not in result.output
    assert _tree(tmp_path) == before


def test_project_inventory_retains_manifest_without_proposal_artifacts(tmp_path: Path) -> None:
    config, project_dir = _project(tmp_path)
    for path in (project_dir / "proposals").iterdir():
        path.unlink()
    before = _tree(tmp_path)

    summaries, invalid = load_project_summaries(config)

    assert [item["project_id"] for item in summaries] == ["research"]
    assert invalid == []
    with pytest.raises(ProjectError, match="Project variant not found"):
        load_project(project_dir)
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("failure", ["yaml", "encoding", "directory"])
def test_project_manifest_read_errors_are_reported_without_breaking_context(
    tmp_path: Path, failure: str
) -> None:
    config, project_dir = _project(tmp_path)
    manifest = project_dir / "project.yaml"
    if failure == "yaml":
        manifest.write_text("project: [private fixture marker\n")
    elif failure == "encoding":
        manifest.write_bytes(b"project: \xff\n")
    else:
        manifest.unlink()
        manifest.mkdir()
    before = _tree(tmp_path)

    with pytest.raises(ProjectError, match="Project manifest"):
        load_project(project_dir)
    result = CliRunner().invoke(app, ["context", "--json", "--config", str(config)])
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert json.loads(result.stdout)["projects"]["invalid"] == [str(project_dir)]
    assert json.loads(result.stdout)["projects"]["count"] == 0
    show = CliRunner().invoke(app, ["project", "show", str(project_dir), "--config", str(config)])
    assert show.exit_code == 1, show.output
    assert "Project manifest" in show.stderr
    assert "private fixture marker" not in show.output
    assert "Traceback" not in show.output
    assert _tree(tmp_path) == before


def test_project_details_use_one_manifest_generation(tmp_path: Path, monkeypatch) -> None:
    _, project_dir = _project(tmp_path)
    manifest = project_dir / "project.yaml"
    expected = load_project_details(project_dir)
    changed = yaml.safe_load(manifest.read_text())
    changed["project"]["id"] = "next-generation"
    changed["project"]["created_at"] = "2026-01-01T00:00:00+00:00"
    original_read = Path.read_bytes
    reads = []

    def replace_after_read(path, *args, **kwargs):
        content = original_read(path, *args, **kwargs)
        if path == manifest:
            reads.append(path)
            path.write_text(yaml.safe_dump(changed))
        return content

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", replace_after_read)
        observed = load_project_details(project_dir)

    assert observed == expected
    assert reads == [manifest]
    refreshed = load_project_details(project_dir)
    assert refreshed.spec.project_id == "next-generation"
    assert refreshed.created_at == "2026-01-01T00:00:00+00:00"
