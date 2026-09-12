"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_project_preparation.py

Verify source preparation preserves inputs and owns only its generated directory.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import shutil
from pathlib import Path

import pytest
import yaml

from cvworkbench.ops.projects import (
    ProjectError,
    append_replace_project_summary_operation,
    guide_project,
    prepare_project_sot,
)
from cvworkbench.ops.scaffold import init_project
from cvworkbench.variants import load_variant


@pytest.fixture
def project(tmp_path):
    init_project(tmp_path, sample_default=True)
    source = tmp_path / "sot.sample"
    (source / "projects.yaml").write_text(
        "projects:\n  - id: study\n    name: Study\n    summary: Original summary.\n    tags: [core]\n"
    )
    config = tmp_path / "config/workbench.yaml"
    job = tmp_path / "job.txt"
    job.write_text("Research scientist with Python experience.\n")
    paths = guide_project(
        config_path=config, job_file=job, variant_id="base", slug="research"
    ).paths
    append_replace_project_summary_operation(
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
    "destination",
    [
        "source",
        "source_parent",
        "project",
        "occupied",
        "file",
        "source_symlink",
        "dangling_symlink",
    ],
)
def test_preparation_rejects_existing_destinations_without_deleting_inputs(project, destination):
    config, source, paths = project
    root = config.parent.parent
    if destination == "occupied":
        target = root / "keep-this"
        target.mkdir()
        (target / "notes.txt").write_text("User-owned notes.\n")
    elif destination in {"file", "source_symlink", "dangling_symlink"}:
        target = root / "keep-this"
        if destination == "file":
            target.write_text("User-owned file.\n")
        else:
            target.symlink_to(source if destination == "source_symlink" else root / "absent")
    else:
        target = {"source": source, "source_parent": source.parent, "project": paths.project_dir}[
            destination
        ]
    before = _tree(root)
    error = None
    try:
        prepare_project_sot(project_dir=paths.project_dir, sot_path=source, target_dir=target)
    except Exception as exc:
        error = exc
    assert _tree(root) == before, "Preparation changed existing input or destination files"
    assert isinstance(error, ProjectError), error
    if destination.endswith("symlink"):
        assert target.is_symlink()


@pytest.mark.parametrize("owner", ["source", "project"])
def test_preparation_rejects_nested_destinations_before_copying(project, monkeypatch, owner):
    config, source, paths = project
    target = (source if owner == "source" else paths.project_dir) / "nested"
    before = _tree(config.parent.parent)

    def forbid_copy(*args, **kwargs):
        raise AssertionError("An overlapping destination must be rejected before copying")

    monkeypatch.setattr(shutil, "copytree", forbid_copy)
    with pytest.raises(ProjectError, match="overlap"):
        prepare_project_sot(project_dir=paths.project_dir, sot_path=source, target_dir=target)
    assert _tree(config.parent.parent) == before


def test_preparation_owns_a_fresh_directory_and_preserves_source(project):
    config, source, paths = project
    source_before = _tree(source)
    target = config.parent.parent / "var/runs/prepared/sot"
    result = prepare_project_sot(project_dir=paths.project_dir, sot_path=source, target_dir=target)
    assert result == target
    data = yaml.safe_load((result / "projects.yaml").read_text())
    assert data["projects"][0]["summary"] == "Tailored summary."
    assert _tree(source) == source_before


@pytest.mark.parametrize("failure", ["copy", "patch", "cancel"])
def test_failed_preparation_removes_only_its_generated_directory(project, monkeypatch, failure):
    config, source, paths = project
    before = _tree(source)
    target = config.parent.parent / "prepared"
    if failure in {"copy", "cancel"}:

        def fail_copy(source_path, destination, *args, **kwargs):
            destination = Path(destination)
            destination.mkdir(exist_ok=True)
            (destination / "partial.txt").write_text("Partial generated output.")
            if failure == "cancel":
                raise KeyboardInterrupt()
            raise OSError("Injected copy failure")

        monkeypatch.setattr(shutil, "copytree", fail_copy)
    else:
        original_copy = shutil.copytree

        def change_copied_source(source_path, destination, *args, **kwargs):
            result = original_copy(source_path, destination, *args, **kwargs)
            if Path(destination) == target:
                (target / "projects.yaml").write_text("projects: []\n")
            return result

        monkeypatch.setattr(shutil, "copytree", change_copied_source)
    with pytest.raises(KeyboardInterrupt if failure == "cancel" else ProjectError):
        prepare_project_sot(project_dir=paths.project_dir, sot_path=source, target_dir=target)
    assert not target.exists()
    assert _tree(source) == before


def test_preparation_does_not_claim_a_destination_created_after_preflight(project, monkeypatch):
    config, source, paths = project
    target = config.parent.parent / "prepared"
    before = _tree(source)
    original_mkdir = Path.mkdir

    def claim_destination(path, *args, **kwargs):
        if path == target:
            original_mkdir(path)
            (path / "notes.txt").write_text("Claimed by another operation.\n")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", claim_destination)
    with pytest.raises(ProjectError, match="destination could not be created"):
        prepare_project_sot(project_dir=paths.project_dir, sot_path=source, target_dir=target)
    assert (target / "notes.txt").read_text() == "Claimed by another operation.\n"
    assert _tree(source) == before


def test_preparation_leaves_a_replaced_destination_intact(project, monkeypatch):
    config, source, paths = project
    target = config.parent.parent / "prepared"
    saved = config.parent.parent / "saved-preparation"
    before = _tree(source)

    def replace_destination(source_path, destination, *args, **kwargs):
        target.mkdir(exist_ok=True)
        target.rename(saved)
        target.mkdir()
        (target / "notes.txt").write_text("Replacement directory.\n")
        raise OSError("Injected copy failure")

    monkeypatch.setattr(shutil, "copytree", replace_destination)
    with pytest.raises(ProjectError, match="Injected copy failure.*replaced"):
        prepare_project_sot(project_dir=paths.project_dir, sot_path=source, target_dir=target)
    assert (target / "notes.txt").read_text() == "Replacement directory.\n"
    assert saved.is_dir()
    assert _tree(source) == before


def test_repeated_preview_preparation_is_temporary_and_refreshes_edits(project, monkeypatch):
    from cvworkbench.dev import preview

    config, source, paths = project
    source_before = _tree(source)
    prepared_paths = []
    original_prepare = preview.prepare_project_sot

    def observe_preparation(**kwargs):
        prepared = original_prepare(**kwargs)
        prepared_paths.append(prepared)
        return prepared

    monkeypatch.setattr(preview, "prepare_project_sot", observe_preparation)
    controller = preview.PreviewController(
        sot_base=source,
        config_path=config,
        variant_id=load_variant(paths.variant_path).id,
        theme_id="default",
        style_preset="modern",
        auto_pdf=False,
        project_dir=paths.project_dir,
    )
    first = controller.build_once()
    assert "Tailored summary." in first.output_files["html"].read_text()
    patch = yaml.safe_load(paths.patch_path.read_text())
    patch["patch"]["operations"][0]["new_text"] = "Updated summary."
    paths.patch_path.write_text(yaml.safe_dump(patch))
    second = controller.rebuild()
    assert second.build_id == first.build_id + 1
    assert "Updated summary." in second.output_files["html"].read_text()
    assert "Tailored summary." not in second.output_files["html"].read_text()
    assert len(set(prepared_paths)) == 2
    assert all(not path.exists() for path in prepared_paths)

    rendered = second.output_files["html"].read_bytes()

    def fail_render(**kwargs):
        raise ValueError("Injected render failure")

    monkeypatch.setattr(preview, "build_documents", fail_render)
    with pytest.raises(preview.PreviewError, match="Injected render failure"):
        controller.rebuild()
    assert len(prepared_paths) == 3
    assert all(not path.exists() for path in prepared_paths)
    assert second.output_files["html"].read_bytes() == rendered
    assert _tree(source) == source_before
