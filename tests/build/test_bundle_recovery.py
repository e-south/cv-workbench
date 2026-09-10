"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_bundle_recovery.py

Verify failed builds preserve complete output bundles and caller-owned run data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from cvworkbench import storage
from cvworkbench.build import artifacts
from cvworkbench.build.pipeline import execute_build
from cvworkbench.build.planning import plan_build
from cvworkbench.build.rendering import RenderError


def _files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


@pytest.mark.parametrize("audited", [True, False])
@pytest.mark.parametrize("layout", ["separate", "shared"])
def test_render_failure_preserves_complete_previous_bundle(
    sample_workspace, tmp_path, audited, layout
):
    source = sample_workspace / "sot.sample"
    config = sample_workspace / "config/workbench.yaml"
    run = tmp_path / "run"
    dist = run if layout == "shared" else tmp_path / "dist"
    plan = plan_build(
        sot_path=source, config_path=config, variant_id="base", formats=["md", "html"]
    )
    execute_build(plan, run_dir=run, dist_dir=dist, write_audit_artifacts=audited)
    (run / "operator-note.txt").write_text("Keep this note\n")
    before = _files(tmp_path)
    person = source / "person.yaml"
    data = yaml.safe_load(person.read_text())
    data["name"] = "Later Person"
    person.write_text(yaml.safe_dump(data))
    style = sample_workspace / "build/themes/default/styles/html/modern.css"
    style.write_text(style.read_text() + "\nbody { color: magenta; }\n")
    plan = plan_build(
        sot_path=source, config_path=config, variant_id="base", formats=["md", "html"]
    )
    failure = sample_workspace / "failure.lua"
    failure.write_text(
        'function Pandoc(doc)\n if FORMAT == "html5" then error("HTML failed") end\n return doc\nend\n'
    )
    plan = replace(plan, filter_paths=(failure,))

    with pytest.raises(RenderError, match="HTML failed"):
        execute_build(plan, run_dir=run, dist_dir=dist, write_audit_artifacts=audited)

    assert _files(tmp_path) == before


def test_failed_build_does_not_retain_an_allocated_run(sample_workspace):
    root = sample_workspace
    plan = plan_build(
        sot_path=root / "sot.sample",
        config_path=root / "config/workbench.yaml",
        variant_id="base",
        formats=["html"],
    )
    failure = root / "failure.lua"
    failure.write_text('function Pandoc(doc) error("HTML failed") end\n')
    plan = replace(plan, filter_paths=(failure,))
    runs = root / "var/runs"
    before = set(runs.iterdir())

    with pytest.raises(RenderError, match="HTML failed"):
        execute_build(plan)

    assert set(runs.iterdir()) == before
    assert not (root / "var/dist/base").exists()


def test_retained_html_run_contains_its_linked_stylesheet(sample_workspace, tmp_path):
    plan = plan_build(
        sot_path=sample_workspace / "sot.sample",
        config_path=sample_workspace / "config/workbench.yaml",
        variant_id="base",
        formats=["html"],
    )
    result = execute_build(plan, run_dir=tmp_path / "run", dist_dir=tmp_path / "dist")
    relative = Path("styles/default-modern.css")
    assert relative.as_posix() in (result.run_dir / "cv.html").read_text()
    assert (result.run_dir / relative).read_bytes() == (result.dist_dir / relative).read_bytes()


@pytest.mark.parametrize("audited", [True, False])
def test_artifact_role_collisions_fail_before_output_writes(sample_workspace, tmp_path, audited):
    plan = plan_build(
        sot_path=sample_workspace / "sot.sample",
        config_path=sample_workspace / "config/workbench.yaml",
        variant_id="base",
        formats=["md"],
    )
    plan = replace(plan, variant=replace(plan.variant, output_name="canonical"))
    target = tmp_path / "bundle"
    with pytest.raises(ValueError, match="Artifact paths overlap"):
        execute_build(plan, run_dir=target, dist_dir=target, write_audit_artifacts=audited)
    assert not target.exists()


def _plan(workspace):
    return plan_build(
        sot_path=workspace / "sot.sample",
        config_path=workspace / "config/workbench.yaml",
        variant_id="base",
        formats=["md", "html"],
    )


def test_alias_run_and_dist_preserve_shared_bundle_semantics(sample_workspace, tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    result = execute_build(_plan(sample_workspace), run_dir=actual, dist_dir=alias)
    manifest = json.loads((actual / "manifest.json").read_text())
    assert "created_at" in manifest
    for fmt, filename in manifest["outputs"].items():
        assert (
            hashlib.sha256((actual / filename).read_bytes()).hexdigest()
            == manifest["output_hashes"][fmt]
        )
    assert result.canonical_path.exists()


def test_failed_metadata_preserves_bundle(sample_workspace, tmp_path, monkeypatch):
    plan = _plan(sample_workspace)
    run, dist = tmp_path / "run", tmp_path / "dist"
    execute_build(plan, run_dir=run, dist_dir=dist)
    before = _files(tmp_path)

    def fail_metadata(**kwargs):
        raise OSError("metadata unavailable")

    monkeypatch.setattr(artifacts, "collect_manifest_metadata", fail_metadata)
    with pytest.raises(OSError, match="metadata unavailable"):
        execute_build(plan, run_dir=run, dist_dir=dist)
    assert _files(tmp_path) == before


@pytest.mark.parametrize("error", [OSError, KeyboardInterrupt])
def test_commit_failure_restores_the_complete_bundle(
    sample_workspace, tmp_path, monkeypatch, error
):
    plan = _plan(sample_workspace)
    run, dist = tmp_path / "run", tmp_path / "dist"
    execute_build(plan, run_dir=run, dist_dir=dist)
    (run / "operator-note.txt").write_text("keep")
    (dist / "cv.md").chmod(0o640)
    before = _files(tmp_path)
    plan = replace(plan, markdown=plan.markdown.replace("Eric", "Changed"))
    replace_file = storage.os.replace
    target = dist / "manifest.json"

    def fail_commit(source, destination):
        if Path(destination) == target and "cvw-stage" in Path(source).name:
            raise error("commit unavailable")
        return replace_file(source, destination)

    monkeypatch.setattr(storage.os, "replace", fail_commit)
    with pytest.raises(storage.AtomicWriteError if error is OSError else error):
        execute_build(plan, run_dir=run, dist_dir=dist)
    assert _files(tmp_path) == before
    assert (dist / "cv.md").stat().st_mode & 0o777 == 0o640


def test_build_rejects_observed_edits_during_real_render(sample_workspace, tmp_path, monkeypatch):
    plan = _plan(sample_workspace)
    run, dist = tmp_path / "run", tmp_path / "dist"
    execute_build(plan, run_dir=run, dist_dir=dist)
    before = _files(tmp_path)
    render = artifacts.render_documents

    def edit_during_render(*args, **kwargs):
        result = render(*args, **kwargs)
        (dist / "cv.md").write_bytes(b"operator edit")
        return result

    monkeypatch.setattr(artifacts, "render_documents", edit_during_render)
    with pytest.raises(storage.AtomicWriteError, match="changed"):
        execute_build(plan, run_dir=run, dist_dir=dist)
    before["dist/cv.md"] = b"operator edit"
    assert _files(tmp_path) == before


def test_failed_commit_removes_only_its_new_run(sample_workspace, monkeypatch):
    plan = _plan(sample_workspace)
    dist = sample_workspace / "var/dist/base"
    runs = sample_workspace / "var/runs"
    before = set(runs.iterdir())
    replace_file = storage.os.replace

    def fail_commit(source, destination):
        if Path(destination) == dist / "manifest.json" and "cvw-stage" in Path(source).name:
            raise OSError("commit unavailable")
        return replace_file(source, destination)

    monkeypatch.setattr(storage.os, "replace", fail_commit)
    with pytest.raises(storage.AtomicWriteError):
        execute_build(plan)
    assert set(runs.iterdir()) == before
    assert not dist.exists()


def test_build_rejects_a_file_symlink_even_when_it_aliases_another_member(
    sample_workspace, tmp_path
):
    run, dist = tmp_path / "run", tmp_path / "dist"
    run.mkdir()
    dist.mkdir()
    (run / "cv.md").write_bytes(b"previous")
    (dist / "cv.md").symlink_to(run / "cv.md")
    with pytest.raises(ValueError, match="symbolic links"):
        execute_build(_plan(sample_workspace), run_dir=run, dist_dir=dist)
    assert (dist / "cv.md").is_symlink()
    assert _files(tmp_path) == {"run/cv.md": b"previous", "dist/cv.md": b"previous"}
