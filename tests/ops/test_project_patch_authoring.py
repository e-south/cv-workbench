"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_project_patch_authoring.py

Verify proposal authoring preserves prior edits and enforces project-owned writes.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from cvworkbench import storage
from cvworkbench.cli import app
from cvworkbench.ops import projects
from cvworkbench.ops.projects import patch_authoring, patches


@pytest.fixture
def proposal(sample_workspace):
    root = sample_workspace
    source = root / "sot.sample"
    (source / "projects.yaml").write_text(
        "projects:\n  - id: study\n    name: Study\n    summary: Original summary.\n    tags: [core]\n"
    )
    job = root / "job.txt"
    job.write_text("Research scientist with Python experience.\n")
    paths = projects.guide_project(
        config_path=root / "config/workbench.yaml", job_file=job, variant_id="base", slug="research"
    ).paths
    return root, source, paths


def _append(source, paths):
    return projects.append_replace_project_summary_operation(
        project_dir=paths.project_dir,
        sot_path=source,
        project_id="study",
        new_text="Tailored summary.",
    )


@pytest.mark.parametrize("error", [OSError, KeyboardInterrupt])
@pytest.mark.parametrize("after_replace", [False, True])
def test_failed_proposal_save_preserves_original_bytes_and_permissions(
    proposal, monkeypatch, error, after_replace
):
    _, source, paths = proposal
    before = paths.patch_path.read_bytes()
    paths.patch_path.chmod(0o600)
    write_text = Path.write_text
    replace = storage.os.replace
    failures = []

    def fail_direct_write(path, text, *args, **kwargs):
        if path == paths.patch_path:
            write_text(path, text[:12], *args, **kwargs)
            failures.append("direct")
            raise error("proposal write failed")
        return write_text(path, text, *args, **kwargs)

    def fail_staged_replace(staged, destination):
        if Path(destination) == paths.patch_path and ".cvw-stage-" in Path(staged).name:
            failures.append("staged")
            if after_replace:
                replace(staged, destination)
            raise error("proposal write failed")
        return replace(staged, destination)

    monkeypatch.setattr(Path, "write_text", fail_direct_write)
    monkeypatch.setattr(storage.os, "replace", fail_staged_replace)
    with pytest.raises((projects.ProjectError, OSError, KeyboardInterrupt)) as caught:
        _append(source, paths)
    assert len(failures) == 1
    assert paths.patch_path.read_bytes() == before
    assert paths.patch_path.stat().st_mode & 0o777 == 0o600
    assert isinstance(
        caught.value, projects.ProjectError if error is OSError else KeyboardInterrupt
    )
    assert not list(paths.patch_path.parent.glob(".*.cvw-*"))


@pytest.mark.parametrize("change", ["edit", "remove"])
def test_independent_proposal_change_is_not_overwritten(proposal, monkeypatch, change):
    _, source, paths = proposal
    compile_ops = patches._compile_project_operations
    observed = []
    independent = (
        b"patch:\n  format: project-ops\n  operations: []\noperator_note: Keep this edit.\n"
    )

    def edit_after_read(**kwargs):
        result = compile_ops(**kwargs)
        if paths.patch_path.with_name("patch.yaml.lock").exists() and not observed:
            observed.append(True)
            if change == "edit":
                paths.patch_path.write_bytes(independent)
            else:
                paths.patch_path.unlink()
        return result

    monkeypatch.setattr(patches, "_compile_project_operations", edit_after_read)
    with pytest.raises(projects.ProjectError, match="changed|update failed"):
        _append(source, paths)
    assert observed == [True]
    if change == "edit":
        assert paths.patch_path.read_bytes() == independent
    else:
        assert not paths.patch_path.exists()


@pytest.mark.parametrize(
    "case",
    ["missing", "encoding", "yaml", "format", "source_guard", "source_yaml", "source_encoding"],
)
def test_invalid_proposal_is_rejected_before_lock_creation(proposal, case):
    _, source, paths = proposal
    if case == "missing":
        paths.patch_path.unlink()
    elif case == "encoding":
        paths.patch_path.write_bytes(b"\xff")
    elif case == "yaml":
        paths.patch_path.write_text("patch: [\n")
    elif case == "format":
        paths.patch_path.write_text("patch:\n  format: unsupported\n  operations: []\n")
    elif case == "source_yaml":
        (source / "projects.yaml").write_text("projects: [\n")
    elif case == "source_encoding":
        (source / "projects.yaml").write_bytes(b"\xff")
    else:
        payload = yaml.safe_load(paths.patch_path.read_text())
        payload["patch"]["operations"] = [
            {
                "op": "replace-project-summary",
                "project_id": "study",
                "old_text": "Stale summary.",
                "new_text": "Another summary.",
            }
        ]
        paths.patch_path.write_text(yaml.safe_dump(payload))
    before = {p.name: p.read_bytes() for p in paths.patch_path.parent.iterdir() if p.is_file()}
    with pytest.raises(projects.ProjectError):
        _append(source, paths)
    assert {
        p.name: p.read_bytes() for p in paths.patch_path.parent.iterdir() if p.is_file()
    } == before


@pytest.mark.parametrize("role", ["patch", "lock", "lock_hardlink", "proposals"])
def test_authoring_rejects_aliased_write_targets_before_mutation(proposal, tmp_path, role):
    _, source, paths = proposal
    outside = tmp_path / "outside"
    outside.mkdir()
    original = paths.patch_path.read_bytes()
    if role == "patch":
        target = outside / "patch.yaml"
        target.write_bytes(original)
        paths.patch_path.unlink()
        paths.patch_path.symlink_to(target)
    elif role in {"lock", "lock_hardlink"}:
        target = outside / "lock"
        target.write_bytes(b"")
        if role == "lock":
            paths.patch_path.with_name("patch.yaml.lock").symlink_to(target)
        else:
            os.link(target, paths.patch_path.with_name("patch.yaml.lock"))
    else:
        paths.patch_path.parent.rename(outside / "proposals")
        paths.patch_path.parent.symlink_to(outside / "proposals", target_is_directory=True)
    before = {
        str(p.relative_to(outside)): p.read_bytes() for p in outside.rglob("*") if p.is_file()
    }
    expected = (
        "inside the project"
        if role == "proposals"
        else "single filesystem link"
        if role == "lock_hardlink"
        else "regular file"
    )
    with pytest.raises(projects.ProjectError, match=expected):
        _append(source, paths)
    assert {
        str(p.relative_to(outside)): p.read_bytes() for p in outside.rglob("*") if p.is_file()
    } == before
    assert paths.patch_path.read_bytes() == original


def test_successful_authoring_retains_document_metadata_and_private_modes(proposal):
    _, source, paths = proposal
    payload = yaml.safe_load(paths.patch_path.read_text())
    payload["operator_note"] = "Keep this proposal note."
    payload["created_at"] = "2026-01-01T00:00:00Z"
    paths.patch_path.write_text(yaml.safe_dump(payload))
    paths.patch_path.chmod(0o600)
    source_before = (source / "projects.yaml").read_bytes()
    _append(source, paths)
    updated = yaml.safe_load(paths.patch_path.read_text())
    assert updated["operator_note"] == payload["operator_note"]
    assert updated["created_at"] == payload["created_at"]
    assert updated["updated_at"]
    assert updated["patch"]["operations"][0]["old_text"] == "Original summary."
    assert paths.patch_path.stat().st_mode & 0o777 == 0o600
    lock = paths.patch_path.with_name("patch.yaml.lock")
    assert lock.read_bytes() == b"\0"
    assert lock.stat().st_mode & 0o777 == 0o600
    assert (source / "projects.yaml").read_bytes() == source_before


def test_non_regular_lock_is_rejected_before_open(proposal, monkeypatch):
    _, source, paths = proposal
    lock = paths.patch_path.with_name("patch.yaml.lock")
    lock.mkdir()
    open_file = patch_authoring.os.open
    opened = []

    def observe_open(path, *args, **kwargs):
        if Path(path) == lock:
            opened.append(path)
        return open_file(path, *args, **kwargs)

    monkeypatch.setattr(patch_authoring.os, "open", observe_open)
    with pytest.raises(projects.ProjectError, match="regular file"):
        _append(source, paths)
    assert opened == []


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="Host does not support filesystem FIFOs")
@pytest.mark.parametrize("role", ["proposal", "source"])
def test_patch_document_rejects_a_fifo_before_reading(tmp_path, monkeypatch, role):
    path = tmp_path / ("patch.yaml" if role == "proposal" else "projects.yaml")
    os.mkfifo(path)
    read_bytes = Path.read_bytes

    def refuse_fifo_read(candidate):
        if candidate == path:
            raise AssertionError("must reject a FIFO before blocking on its contents")
        return read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", refuse_fifo_read)
    with pytest.raises(projects.ProjectError, match="regular file"):
        if role == "proposal":
            patches.read_project_patch_document(path)
        else:
            patches.read_project_summary_text(sot_path=tmp_path, project_id="study")


def test_process_writer_reloads_the_proposal_after_waiting_for_its_lock(proposal):
    _, source, paths = proposal
    source_file = source / "projects.yaml"
    facts = yaml.safe_load(source_file.read_text())
    facts["projects"].append(
        {"id": "second", "name": "Second study", "summary": "Second original.", "tags": ["core"]}
    )
    source_file.write_text(yaml.safe_dump(facts))
    source_before = source_file.read_bytes()
    child = """
import sys
from pathlib import Path
from cvworkbench.ops.projects import patch_authoring
lock = patch_authoring._lock_project_patch_handle
def observed(handle):
    print('LOCK_WAIT', flush=True)
    return lock(handle)
patch_authoring._lock_project_patch_handle = observed
patch_authoring.append_replace_project_summary_operation(
    project_dir=Path(sys.argv[1]), sot_path=Path(sys.argv[2]),
    project_id='study', new_text='Tailored summary.')
"""
    process = None
    try:
        with patch_authoring._project_patch_authoring_lock(paths.patch_path):
            process = subprocess.Popen(
                [sys.executable, "-c", child, str(paths.project_dir), str(source)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            with pytest.raises(subprocess.TimeoutExpired) as waiting:
                process.communicate(timeout=2)
            assert waiting.value.output == b"LOCK_WAIT\n"
            payload = yaml.safe_load(paths.patch_path.read_text())
            payload["patch"]["operations"] = [
                {
                    "op": "replace-project-summary",
                    "project_id": "second",
                    "old_text": "Second original.",
                    "new_text": "Second tailored.",
                }
            ]
            paths.patch_path.write_text(yaml.safe_dump(payload))
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr
        assert stdout == "LOCK_WAIT\n"
        assert stderr == ""
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
    operations = yaml.safe_load(paths.patch_path.read_text())["patch"]["operations"]
    assert [operation["project_id"] for operation in operations] == ["second", "study"]
    assert source_file.read_bytes() == source_before


@pytest.mark.parametrize("failure", ["encoding", "lock_symlink", "intervening_edit"])
def test_cli_authoring_reports_failures_without_partial_json(
    proposal, tmp_path, monkeypatch, failure
):
    root, _, paths = proposal
    if failure == "encoding":
        paths.patch_path.write_bytes(b"\xff")
    elif failure == "lock_symlink":
        outside = tmp_path / "operator-note"
        outside.write_bytes(b"")
        paths.patch_path.with_name("patch.yaml.lock").symlink_to(outside)
    else:
        compile_ops = patches._compile_project_operations

        def edit_after_read(**kwargs):
            result = compile_ops(**kwargs)
            if paths.patch_path.with_name("patch.yaml.lock").exists():
                paths.patch_path.write_text(
                    "patch:\n  format: project-ops\n  operations: []\nnote: Preserve this edit.\n"
                )
            return result

        monkeypatch.setattr(patches, "_compile_project_operations", edit_after_read)
    result = CliRunner().invoke(
        app,
        [
            "project",
            "patch",
            "replace-project-summary",
            "research",
            "--project-id",
            "study",
            "--new-text",
            "Tailored summary.",
            "--config",
            str(root / "config/workbench.yaml"),
            "--json",
        ],
    )
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.startswith("ERROR: Project patch")
    if failure == "lock_symlink":
        assert outside.read_bytes() == b""
    elif failure == "intervening_edit":
        assert yaml.safe_load(paths.patch_path.read_text())["note"] == "Preserve this edit."
