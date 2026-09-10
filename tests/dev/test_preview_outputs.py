"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/dev/test_preview_outputs.py

Verify preview artifacts preserve audited builds and independent review surfaces.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from pathlib import Path

import pytest
import yaml

from cvworkbench.build.pipeline import build_documents
from cvworkbench.dev.preview import PreviewController, PreviewError
from cvworkbench.ops.projects import create_project_from_file, load_project
from cvworkbench.ops.runs import scan_runs
from cvworkbench.variants import load_variant


def _files(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _rename_person(root: Path, name: str) -> None:
    path = root / "sot.sample/person.yaml"
    data = yaml.safe_load(path.read_text())
    data["name"] = name
    path.write_text(yaml.safe_dump(data))


def _controller(root: Path, project: Path | None = None) -> PreviewController:
    return PreviewController(
        sot_base=root / "sot.sample",
        config_path=root / "config/workbench.yaml",
        variant_id=load_variant(load_project(project).variant_path).id if project else "base",
        theme_id="default",
        style_preset="modern",
        output_format="md",
        auto_pdf=False,
        project_dir=project,
        session_id="same-browser-lease",
    )


def _project(root: Path) -> Path:
    job = root / "job.txt"
    job.write_text("Research scientist using Python and experimental design.\n")
    created = create_project_from_file(
        job_path=job,
        slug="base",
        base_variant_id="base",
        config_path=root / "config/workbench.yaml",
        sot_path=root / "sot.sample",
        store_raw=False,
    )
    return created.project_dir


def test_preview_preserves_audited_build_and_manifest(sample_workspace):
    root = sample_workspace
    build = build_documents(
        sot_path=root / "sot.sample",
        config_path=root / "config/workbench.yaml",
        variant_id="base",
        formats=["md", "html"],
    )
    before_dist, before_run = _files(build.dist_dir), _files(build.run_dir)
    _rename_person(root, "Preview Person")
    style = root / "build/themes/default/styles/html/modern.css"
    style.write_text(style.read_text() + "\nbody { color: magenta; }\n")
    state = _controller(root).build_once()
    assert "Preview Person" in state.output_files["html"].read_text()
    assert _files(build.dist_dir) == before_dist
    assert _files(build.run_dir) == before_run
    assert state.dist_dir.is_relative_to(root / "var/runs/preview/variants/base")
    catalog = scan_runs(root / "config/workbench.yaml")
    assert len(catalog.runs) == 1
    assert not catalog.invalid


@pytest.mark.parametrize("project", [False, True])
def test_independent_controllers_preserve_previous_preview(sample_workspace, project):
    root = sample_workspace
    project_dir = _project(root) if project else None
    first = _controller(root, project_dir).build_once()
    before = _files(first.dist_dir)
    _rename_person(root, "Another Preview")
    second = _controller(root, project_dir).build_once()
    assert "Another Preview" in second.output_files["html"].read_text()
    assert first.dist_dir != second.dist_dir
    assert _files(first.dist_dir) == before
    scope = "projects" if project else "variants"
    assert first.dist_dir.is_relative_to(root / "var/runs/preview" / scope / "base")


def test_preview_separates_canonical_input_from_served_output(sample_workspace):
    root = sample_workspace
    controller = _controller(root, _project(root))
    first = controller.build_once()
    assert not (first.dist_dir / "canonical.md").exists()
    canonical = first.dist_dir.parent / "input/canonical.md"
    assert canonical.is_file()
    assert "styles/default-modern.css" in first.output_files["html"].read_text()
    assert (first.dist_dir / "styles/default-modern.css").is_file()
    _rename_person(root, "Rebuilt Preview")
    second = controller.rebuild()
    assert second.dist_dir == first.dist_dir
    assert second.build_id == first.build_id + 1
    assert "Rebuilt Preview" in canonical.read_text()
    assert not (second.dist_dir / "manifest.json").exists()


def test_render_failure_is_reported_with_previous_preview_intact(sample_workspace):
    root = sample_workspace
    controller = _controller(root)
    previous = controller.build_once()
    before = _files(previous.dist_dir.parent)
    _rename_person(root, "Failed Change")
    failure = root / "failure.lua"
    failure.write_text('function Pandoc(doc) error("preview render failed") end\n')
    defaults_file = root / "build/themes/default/pandoc/html.defaults.yaml"
    defaults = yaml.safe_load(defaults_file.read_text())
    defaults["filters"] = [str(failure)]
    defaults_file.write_text(yaml.safe_dump(defaults))

    with pytest.raises(PreviewError, match="preview render failed"):
        controller.rebuild()
    assert _files(previous.dist_dir.parent) == before
    assert controller.state().build_id == previous.build_id
    assert "preview render failed" in controller.state().last_error


def test_invalid_project_source_does_not_allocate_preview_artifacts(sample_workspace):
    root = sample_workspace
    controller = _controller(root, _project(root))
    before = _files(root / "var/runs/preview")
    (root / "sot.sample/person.yaml").unlink()
    with pytest.raises(PreviewError, match="person.yaml"):
        controller.build_once()
    assert _files(root / "var/runs/preview") == before
    assert not (root / "var/runs/preview/projects").exists()
    assert controller.state().build_id == 0
    assert not controller.state().output_files
