"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_project_artifacts.py

Verify stored job artifacts against their recorded bytes without changing the project.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import hashlib
import os
from pathlib import Path

import pytest

from cvworkbench.ops import projects
from cvworkbench.ops.projects import artifacts
from cvworkbench.ops.scaffold import init_project


def _project(root: Path):
    init_project(root, sample_default=True)
    job = root / "job.txt"
    job.write_text("Research scientist with Python experience.\n")
    return projects.create_project_from_file(
        job_path=job,
        slug="research",
        base_variant_id="base",
        config_path=root / "config/workbench.yaml",
        sot_path=root / "sot.sample",
        store_raw=False,
    )


@pytest.mark.parametrize("artifact", ["extracted_text", "signals"])
@pytest.mark.parametrize("state", ["matches_record", "changed", "missing", "unreadable"])
def test_artifact_inspection_reports_observed_state_without_writes(tmp_path, artifact, state):
    project = _project(tmp_path)
    path = project.extracted_path if artifact == "extracted_text" else project.signals_path
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if state == "changed":
        path.write_text("changed-private-fixture-marker\n")
    elif state == "missing":
        path.unlink()
    elif state == "unreadable":
        path.unlink()
        path.mkdir()
    before = {
        item.relative_to(tmp_path): item.read_bytes()
        for item in tmp_path.rglob("*")
        if item.is_file()
    }

    checks = projects.inspect_project_artifacts(project.project_dir)

    assert len(checks) == 2
    check = next(item for item in checks if item.name == artifact)
    assert check.state == state
    assert check.recorded_sha256 == original_hash
    if state == "matches_record":
        assert check.observed_sha256 == original_hash
        assert check.error is None
    elif state == "changed":
        assert (
            check.observed_sha256 == hashlib.sha256(b"changed-private-fixture-marker\n").hexdigest()
        )
    else:
        assert check.observed_sha256 is None
    assert "changed-private-fixture-marker" not in (check.error or "")
    other = next(item for item in checks if item.name != artifact)
    assert other.state == "matches_record"
    assert {
        item.relative_to(tmp_path): item.read_bytes()
        for item in tmp_path.rglob("*")
        if item.is_file()
    } == before


def test_artifact_inspection_does_not_require_retained_proposals(tmp_path):
    project = _project(tmp_path)
    project.variant_path.unlink()
    project.patch_path.unlink()

    checks = projects.inspect_project_artifacts(project.project_dir)

    assert len(checks) == 2
    assert all(item.state == "matches_record" for item in checks)


def test_artifact_inspection_reports_read_denial_without_echo(tmp_path, monkeypatch):
    project = _project(tmp_path)
    original_open = Path.open

    def deny_artifact(path, *args, **kwargs):
        if path == project.signals_path:
            raise PermissionError("private-fixture-marker")
        return original_open(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", deny_artifact)
        checks = projects.inspect_project_artifacts(project.project_dir)

    check = next(item for item in checks if item.name == "signals")
    assert check.state == "unreadable"
    assert check.observed_sha256 is None
    assert "private-fixture-marker" not in check.error


def test_project_details_include_artifact_checks_from_its_manifest_read(tmp_path, monkeypatch):
    project = _project(tmp_path)
    reads = []
    original_read = Path.read_bytes

    def observe_manifest_read(path, *args, **kwargs):
        if path == project.project_file:
            reads.append(path)
        return original_read(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", observe_manifest_read)
        details = projects.load_project_details(project.project_dir)

    assert reads == [project.project_file]
    assert len(details.artifact_checks) == 2
    assert all(item.state == "matches_record" for item in details.artifact_checks)


def test_artifact_inspection_rejects_fifo_without_opening_it(tmp_path, monkeypatch):
    project = _project(tmp_path)
    project.signals_path.unlink()
    os.mkfifo(project.signals_path)
    original_open = Path.open

    def reject_fifo_open(path, *args, **kwargs):
        if path == project.signals_path:
            raise AssertionError("Artifact inspection must not open a named pipe")
        return original_open(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", reject_fifo_open)
        checks = projects.inspect_project_artifacts(project.project_dir)

    assert checks[1].state == "unreadable"
    assert "regular file" in checks[1].error


def test_artifact_inspection_rechecks_ownership_after_metadata_capture(tmp_path, monkeypatch):
    project = _project(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside-private-fixture-marker\n")
    original_metadata = artifacts._project_metadata
    original_open = Path.open

    def replace_with_outside_link(*args, **kwargs):
        metadata = original_metadata(*args, **kwargs)
        project.signals_path.unlink()
        project.signals_path.symlink_to(outside)
        return metadata

    def reject_outside_read(path, *args, **kwargs):
        if path.resolve() == outside:
            raise AssertionError("Artifact inspection must not read outside the project")
        return original_open(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(artifacts, "_project_metadata", replace_with_outside_link)
        patch.setattr(Path, "open", reject_outside_read)
        checks = projects.inspect_project_artifacts(project.project_dir)

    assert checks[1].state == "unreadable"
    assert "within the project directory" in checks[1].error
    assert "outside-private-fixture-marker" not in checks[1].error
