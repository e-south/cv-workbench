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
from cvworkbench.workspace.context import inspect_workspace
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


@pytest.mark.parametrize(
    "field,value",
    [
        ("created_at", None),
        ("created_at", True),
        ("created_at", 42),
        ("created_at", {}),
        ("created_at", "yesterday"),
        ("created_at", "2026-01-01"),
        ("job.source.type", None),
        ("job.source.type", False),
        ("job.source.type", ["file"]),
        ("job.source.type", "email"),
        ("job.source.value", None),
        ("job.source.value", False),
        ("job.source.value", 42),
        ("job.source.value", {"private": "fixture-marker"}),
        ("signals.hash", None),
        ("signals.hash", False),
        ("signals.hash", []),
        ("signals.hash", "cafebabe"),
        ("job.extracted_hash", None),
        ("job.extracted_hash", False),
        ("job.extracted_hash", "deadbeef"),
        ("job.raw_path", False),
        ("job.raw_path", 0),
        ("job.raw_path", []),
        ("job.raw_path", ""),
    ],
)
def test_project_details_reject_malformed_descriptive_metadata(
    tmp_path: Path, field: str, value: object
) -> None:
    _, project_dir = _project(tmp_path)
    manifest = project_dir / "project.yaml"
    payload = yaml.safe_load(manifest.read_text())
    cursor = payload["project"]
    parts = field.split(".")
    for key in parts[:-1]:
        cursor = cursor[key]
    cursor[parts[-1]] = value
    manifest.write_text(yaml.safe_dump(payload))
    before = _tree(tmp_path)

    with pytest.raises(ProjectError) as caught:
        load_project_details(project_dir)

    assert field in str(caught.value)
    assert "fixture-marker" not in str(caught.value)
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("field,value", [("created_at", {}), ("source_value", {"marker"})])
def test_inventory_preserves_identity_and_reports_invalid_description(tmp_path, field, value):
    config, project_dir = _project(tmp_path)
    manifest = project_dir / "project.yaml"
    payload = yaml.safe_load(manifest.read_text())
    if field == "created_at":
        payload["project"]["created_at"] = value
    else:
        payload["project"]["job"]["source"]["value"] = value
    manifest.write_text(yaml.safe_dump(payload))
    before = _tree(tmp_path)

    result = CliRunner().invoke(app, ["context", "--json", "--config", str(config)])

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    projects = json.loads(result.stdout)["projects"]
    assert projects["invalid"] == []
    assert projects["count"] == 1
    item = projects["items"][0]
    assert item["project_id"] == "research"
    assert item["created_at" if field == "created_at" else "job_source"] is None
    assert item["metadata_errors"]
    compact = CliRunner().invoke(app, ["context", "--json", "--compact", "--config", str(config)])
    assert compact.exit_code == 0, compact.output
    compact_projects = json.loads(compact.stdout)["projects"]
    assert compact_projects["metadata_error_count"] == 1
    assert "metadata_errors=1" in compact_projects["summary"]
    strict = inspect_workspace(config=config, sot_path=None, strict=True, compact=False)
    assert strict["projects"]["metadata_error_count"] == 1
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("route", ["absolute", "relative", "symlink"])
def test_project_inspection_does_not_read_guidance_outside_its_workspace(
    tmp_path: Path, monkeypatch, route: str
) -> None:
    config, project_dir = _project(tmp_path)
    outside = tmp_path / "outside-project"
    outside.mkdir()
    secret_plan = outside / "proposal-plan.json"
    secret_plan.write_text(json.dumps({"summary": "outside-private-fixture-marker"}))
    if route == "absolute":
        signals_path = str(outside / "signals.json")
    elif route == "relative":
        signals_path = "../../../outside-project/signals.json"
    else:
        (project_dir / "outside-link").symlink_to(outside, target_is_directory=True)
        signals_path = "outside-link/signals.json"
    manifest = project_dir / "project.yaml"
    payload = yaml.safe_load(manifest.read_text())
    payload["project"]["signals"]["path"] = signals_path
    manifest.write_text(yaml.safe_dump(payload))
    before = _tree(tmp_path)
    outside_reads = []
    original_read = Path.read_text

    def observe_read(path, *args, **kwargs):
        if path.resolve() == secret_plan:
            outside_reads.append(path)
        return original_read(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", observe_read)
        result = CliRunner().invoke(
            app, ["project", "show", str(project_dir), "--config", str(config), "--json"]
        )

    assert outside_reads == []
    assert result.exit_code == 1, result.output
    assert "signals.path" in result.stderr
    assert "outside-private-fixture-marker" not in result.output
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("route", ["absolute", "symlink"])
def test_project_details_accept_internal_artifact_references(tmp_path: Path, route: str) -> None:
    _, project_dir = _project(tmp_path)
    manifest = project_dir / "project.yaml"
    payload = yaml.safe_load(manifest.read_text())
    signals = project_dir / "job/signals.json"
    if route == "absolute":
        payload["project"]["signals"]["path"] = str(signals)
    else:
        (project_dir / "job-link").symlink_to(project_dir / "job", target_is_directory=True)
        payload["project"]["signals"]["path"] = "job-link/signals.json"
    manifest.write_text(yaml.safe_dump(payload))

    assert load_project_details(project_dir).signals_path == signals


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
