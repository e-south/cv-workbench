"""Verify application edits and reports the selected source version."""

import difflib
import json

import pytest
import yaml
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.ops import apply as draft_application
from cvworkbench.ops.projects import patches as project_application

ORIGINAL = "projects:\n  - id: study\n    summary: Original summary.\n"
REPLACEMENT = "Reviewed summary."


@pytest.fixture
def versioned_edit(tmp_path):
    source = tmp_path / "sot"
    for directory in (source, source / "versions/base", source / "versions/review"):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "projects.yaml").write_text(ORIGINAL)
    (source / "ACTIVE").write_text("review\n")
    project = tmp_path / "project"
    proposal = project / "proposals"
    proposal.mkdir(parents=True)
    (project / "project.yaml").write_text(
        yaml.safe_dump(
            {"project": {"id": "study", "base_variant": "base", "sot_path": str(source)}}
        )
    )
    (proposal / "variant.yaml").write_text("variant:\n  id: proposal-study\n")
    patch = {
        "patch": {
            "format": "project-ops",
            "operations": [
                {
                    "op": "replace-project-summary",
                    "project_id": "study",
                    "old_text": "Original summary.",
                    "new_text": REPLACEMENT,
                }
            ],
        }
    }
    (proposal / "patch.yaml").write_text(yaml.safe_dump(patch))
    config = tmp_path / "config/workbench.yaml"
    config.parent.mkdir()
    config.write_text("paths: {}\n")
    draft = tmp_path / "draft"
    draft.mkdir()
    return source, project, draft, config


def _command(workspace, kind, selected):
    source, project, draft, config = workspace
    if kind.startswith("project"):
        args = ["project", "apply", str(project), "--config", str(config)]
        if kind == "project-override":
            args += ["--sot-path", str(selected)]
        else:
            manifest = project / "project.yaml"
            data = yaml.safe_load(manifest.read_text())
            data["project"]["sot_path"] = str(selected)
            manifest.write_text(yaml.safe_dump(data))
    else:
        if kind == "draft-ops":
            (draft / "patch.yaml").write_bytes((project / "proposals/patch.yaml").read_bytes())
        else:
            diff = difflib.unified_diff(
                ORIGINAL.splitlines(keepends=True),
                ORIGINAL.replace("Original summary.", REPLACEMENT).splitlines(keepends=True),
                fromfile="projects.yaml",
                tofile="projects.yaml",
            )
            (draft / "patch.diff").write_text("".join(diff))
        args = ["apply", "--draft", str(draft), "--sot-path", str(selected)]
    return [*args, "--json"]


@pytest.mark.parametrize("kind", ["draft-ops", "draft-diff", "project", "project-override"])
@pytest.mark.parametrize("selection", ["active", "pinned"])
def test_apply_edits_only_selected_version_and_reports_it(versioned_edit, kind, selection):
    source, _, _, _ = versioned_edit
    selected = source if selection == "active" else source / "versions/base"
    expected = source / "versions/review" if selection == "active" else selected
    untouched = source / "versions/base" if selection == "active" else source / "versions/review"

    result = CliRunner().invoke(app, _command(versioned_edit, kind, selected))

    assert result.exit_code == 0, result.output
    assert REPLACEMENT in (expected / "projects.yaml").read_text()
    assert (source / "projects.yaml").read_text() == ORIGINAL
    assert (untouched / "projects.yaml").read_text() == ORIGINAL
    assert (source / "ACTIVE").read_text() == "review\n"
    assert json.loads(result.stdout)["data"]["sot_path"] == str(expected)


@pytest.mark.parametrize("kind", ["draft-ops", "project"])
@pytest.mark.parametrize(
    "broken", ["missing-active", "missing-versions", "file-version", "invalid-text", "escape"]
)
def test_apply_rejects_invalid_version_selection_without_writes(versioned_edit, kind, broken):
    source, _, _, _ = versioned_edit
    args = _command(versioned_edit, kind, source)
    active = source / "ACTIVE"
    if broken == "missing-active":
        active.unlink()
    elif broken == "missing-versions":
        (source / "versions").rename(source / "retained-versions")
    elif broken == "file-version":
        (source / "versions/file").write_text("not a source directory\n")
        active.write_text("file\n")
    elif broken == "invalid-text":
        active.write_bytes(b"\xff")
    else:
        external = source.parent / "other-source"
        external.mkdir()
        (external / "projects.yaml").write_text(ORIGINAL)
        (source / "versions/linked").symlink_to(external, target_is_directory=True)
        active.write_text("linked\n")
    before = {p: p.read_bytes() for p in source.parent.rglob("*") if p.is_file()}

    result = CliRunner().invoke(app, args)

    assert result.exit_code == 1, result.output
    assert "ERROR: " in result.stderr
    assert "SoT" in result.stderr
    assert {p: p.read_bytes() for p in source.parent.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("kind", ["draft-ops", "project"])
def test_apply_keeps_selected_version_when_active_changes_after_selection(
    versioned_edit, monkeypatch, kind
):
    source, project, draft, _ = versioned_edit
    _command(versioned_edit, kind, source)
    owner = draft_application if kind == "draft-ops" else project_application
    function = "load_project_patch_payload" if kind == "draft-ops" else "load_project_patch"
    original = getattr(owner, function)

    def switch_active(*args, **kwargs):
        (source / "ACTIVE").write_text("base\n")
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, function, switch_active)
    if kind == "draft-ops":
        selected = draft_application.apply_draft(draft_dir=draft, sot_path=source).sot_path
    else:
        selected = project_application.apply_project_patch(project_dir=project, sot_path=source)

    assert selected == source / "versions/review"
    assert REPLACEMENT in (selected / "projects.yaml").read_text()
    assert (source / "versions/base/projects.yaml").read_text() == ORIGINAL
    assert (source / "projects.yaml").read_text() == ORIGINAL
    assert (source / "ACTIVE").read_text() == "base\n"
