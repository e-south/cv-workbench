"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_project_retarget.py

Verifies retarget input consistency and preservation of intervening edits.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from pathlib import Path

import pytest
import yaml

from cvworkbench.ops.projects import (
    ProjectError,
    create_project_from_file,
    retarget_project_variant,
)
from cvworkbench.ops.scaffold import init_project


def _project(root: Path):
    init_project(root, sample_default=True)
    config = root / "config/workbench.yaml"
    (config.parent / "variants/focus.yaml").write_text(
        "variant:\n  id: focus\n  outputs: [md]\n  include_tags: [leadership]\n"
    )
    job = root / "job.txt"
    job.write_text("Research scientist with Python experience.\n")
    project = create_project_from_file(
        job_path=job,
        slug="job",
        base_variant_id="base",
        config_path=config,
        sot_path=root / "sot.sample",
        store_raw=False,
    )
    return config, project


@pytest.mark.parametrize("changed_file", ["manifest", "proposal"])
def test_retarget_preserves_an_intervening_edit(
    tmp_path: Path, monkeypatch, changed_file: str
) -> None:
    config, project = _project(tmp_path)
    target = project.project_file if changed_file == "manifest" else project.variant_path
    original = {p: p.read_bytes() for p in (project.project_file, project.variant_path)}
    edited = yaml.safe_load(original[target])
    if changed_file == "manifest":
        edited["project"]["id"] = "../../unvalidated"
    else:
        edited["variant"]["output_name"] = "Edited proposal"
    edited_bytes = yaml.safe_dump(edited).encode("utf-8")
    original_text = Path.read_text
    original_bytes = Path.read_bytes
    changed = False

    def edit_after_read(path, result):
        nonlocal changed
        if path == target and not changed:
            changed = True
            target.write_bytes(edited_bytes)
        return result

    def read_text(path, *args, **kwargs):
        return edit_after_read(path, original_text(path, *args, **kwargs))

    def read_bytes(path):
        return edit_after_read(path, original_bytes(path))

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", read_text)
        patch.setattr(Path, "read_bytes", read_bytes)
        with pytest.raises(ProjectError):
            retarget_project_variant(
                project_dir=project.project_dir, base_variant_id="focus", config_path=config
            )

    assert changed
    assert target.read_bytes() == edited_bytes
    for path, content in original.items():
        if path != target:
            assert path.read_bytes() == content
    assert not list(project.project_dir.rglob("*.cvw-*"))


@pytest.mark.parametrize("invalid", ["proposal_yaml", "proposal_utf8", "base_schema"])
def test_retarget_reports_invalid_inputs_without_echo_or_writes(
    tmp_path: Path, invalid: str
) -> None:
    config, project = _project(tmp_path)
    if invalid == "proposal_yaml":
        project.variant_path.write_text("variant: [private-fixture-marker\n")
    elif invalid == "proposal_utf8":
        project.variant_path.write_bytes(b"variant: \xff\n")
    else:
        (config.parent / "variants/focus.yaml").write_text(
            "variant:\n  id: focus\n  outputs: [md]\n  output_name: ../outside\n"
        )
    before = {p: p.read_bytes() for p in (project.project_file, project.variant_path)}

    with pytest.raises(ProjectError) as caught:
        retarget_project_variant(
            project_dir=project.project_dir, base_variant_id="focus", config_path=config
        )

    assert "private-fixture-marker" not in str(caught.value)
    assert {p: p.read_bytes() for p in before} == before
    assert not list(project.project_dir.rglob("*.cvw-*"))
