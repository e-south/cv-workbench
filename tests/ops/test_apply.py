"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_apply.py

Tests applying draft patches to SoT.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from cvworkbench.cli import app


def test_apply_updates_sot(tmp_path: Path) -> None:
    sot_path = tmp_path / "sot"
    sot_path.mkdir()
    _write_minimal_sot(sot_path)

    draft_dir = tmp_path / "draft"
    draft_dir.mkdir()
    patch_path = draft_dir / "patch.diff"
    before = ["id: sample\n", "name: Sample User\n"]
    after = ["id: sample\n", "name: Updated User\n"]
    diff = difflib.unified_diff(before, after, fromfile="person.yaml", tofile="person.yaml")
    patch_path.write_text("".join(diff))

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "apply",
            "--draft",
            str(draft_dir),
            "--sot-path",
            str(sot_path),
        ],
    )

    assert result.exit_code == 0
    assert "Updated User" in (sot_path / "person.yaml").read_text()


def test_apply_rejects_patch_targets_outside_sot(tmp_path: Path) -> None:
    sot_path = tmp_path / "sot"
    sot_path.mkdir()
    _write_minimal_sot(sot_path)
    (tmp_path / "outside.txt").write_text("outside\n")

    draft_dir = tmp_path / "draft"
    draft_dir.mkdir()
    patch_path = draft_dir / "patch.diff"
    diff = difflib.unified_diff(
        ["outside\n"],
        ["changed\n"],
        fromfile="../outside.txt",
        tofile="../outside.txt",
    )
    patch_path.write_text("".join(diff))

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "apply",
            "--draft",
            str(draft_dir),
            "--sot-path",
            str(sot_path),
        ],
    )

    assert result.exit_code != 0
    assert "outside SoT" in (result.stderr or "")


def test_apply_rejects_review_diff_patches_that_do_not_target_sot_files(tmp_path: Path) -> None:
    sot_path = tmp_path / "sot"
    sot_path.mkdir()
    _write_minimal_sot(sot_path)

    draft_dir = tmp_path / "draft"
    draft_dir.mkdir()
    patch_path = draft_dir / "patch.diff"
    diff = difflib.unified_diff(
        ["before\n"],
        ["after\n"],
        fromfile="canonical.md",
        tofile="imported.md",
    )
    patch_path.write_text("".join(diff))

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "apply",
            "--draft",
            str(draft_dir),
            "--sot-path",
            str(sot_path),
        ],
    )

    assert result.exit_code != 0
    assert "Patch target does not exist under SoT: canonical.md" in (result.stderr or "")


def test_apply_rejects_review_diff_only_drafts(tmp_path: Path) -> None:
    sot_path = tmp_path / "sot"
    sot_path.mkdir()
    _write_minimal_sot(sot_path)

    draft_dir = tmp_path / "draft"
    draft_dir.mkdir()
    (draft_dir / "draft.json").write_text(
        json.dumps(
            {
                "apply_status": "review_diff_only",
                "patch_path": "patch.diff",
            }
        )
        + "\n"
    )
    (draft_dir / "notes.md").write_text(
        "# Import Notes\n\n- apply_status: review_diff_only\n",
    )
    patch_path = draft_dir / "patch.diff"
    before = ["id: sample\n", "name: Sample User\n"]
    after = ["id: sample\n", "name: Updated User\n"]
    diff = difflib.unified_diff(before, after, fromfile="person.yaml", tofile="person.yaml")
    patch_path.write_text("".join(diff))

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "apply",
            "--draft",
            str(draft_dir),
            "--sot-path",
            str(sot_path),
        ],
    )

    assert result.exit_code != 0
    assert "review_diff_only" in (result.stderr or "")
    assert "Sample User" in (sot_path / "person.yaml").read_text()


def test_apply_rejects_import_draft_without_metadata(tmp_path: Path) -> None:
    sot_path = tmp_path / "sot"
    sot_path.mkdir()
    _write_minimal_sot(sot_path)

    draft_dir = tmp_path / "draft"
    draft_dir.mkdir()
    (draft_dir / "imported.md").write_text("# Imported\n")
    (draft_dir / "notes.md").write_text("# Import Notes\n")
    (draft_dir / "patch.diff").write_text("")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "apply",
            "--draft",
            str(draft_dir),
            "--sot-path",
            str(sot_path),
        ],
    )

    assert result.exit_code != 0
    assert "draft.json" in (result.stderr or "")


def test_apply_accepts_project_ops_patch_yaml(tmp_path: Path) -> None:
    sot_path = tmp_path / "sot"
    sot_path.mkdir()
    _write_minimal_sot(sot_path)

    draft_dir = tmp_path / "draft"
    draft_dir.mkdir()
    (draft_dir / "patch.yaml").write_text(
        "\n".join(
            [
                "patch:",
                "  format: project-ops",
                "  operations:",
                "    - op: replace-experience-bullet",
                "      role_id: role-1",
                "      bullet_id: bullet-1",
                "      old_text: Delivered outcomes.",
                "      new_text: Delivered measurable outcomes.",
                "    - op: replace-project-summary",
                "      project_id: project-1",
                "      old_text: Example summary.",
                "      new_text: Tailored project summary.",
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "apply",
            "--draft",
            str(draft_dir),
            "--sot-path",
            str(sot_path),
        ],
    )

    assert result.exit_code == 0
    assert "Delivered measurable outcomes." in (sot_path / "experience.yaml").read_text()
    assert "Tailored project summary." in (sot_path / "projects.yaml").read_text()


def test_apply_reports_compiled_noop_reason_for_project_ops(tmp_path: Path) -> None:
    sot_path = tmp_path / "sot"
    sot_path.mkdir()
    (sot_path / "experience.yaml").write_text(
        yaml.safe_dump(
            {
                "roles": [
                    {
                        "id": "role-1",
                        "company": "Example Co",
                        "title": "Engineer",
                        "start": 2021,
                        "bullets": [
                            {
                                "id": "bullet-1",
                                "text": "Delivered outcomes.",
                                "tags": ["impact"],
                            }
                        ],
                    }
                ]
            },
            sort_keys=False,
        )
    )

    draft_dir = tmp_path / "draft"
    draft_dir.mkdir()
    (draft_dir / "patch.yaml").write_text(
        "\n".join(
            [
                "patch:",
                "  format: project-ops",
                "  operations:",
                "    - op: replace-experience-bullet",
                "      role_id: role-1",
                "      bullet_id: bullet-1",
                "      old_text: Delivered outcomes.",
                "      new_text: Delivered outcomes.",
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "apply",
            "--draft",
            str(draft_dir),
            "--sot-path",
            str(sot_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["status"] == "no_changes"
    assert payload["data"]["reason"] == "compiled_noop"
    assert "Delivered outcomes." in (sot_path / "experience.yaml").read_text()


def _write_minimal_sot(sot_path: Path) -> None:
    (sot_path / "person.yaml").write_text("id: sample\nname: Sample User\n")
    (sot_path / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role-1",
                "    company: Example Co",
                "    title: Engineer",
                "    start: 2021-01",
                "    bullets:",
                "      - id: bullet-1",
                "        text: Delivered outcomes.",
                "        tags:",
                "          - impact",
            ]
        )
        + "\n"
    )
    (sot_path / "projects.yaml").write_text(
        "\n".join(
            [
                "projects:",
                "  - id: project-1",
                "    name: Example Project",
                "    summary: Example summary.",
                "    tags:",
                "      - sample",
            ]
        )
        + "\n"
    )
    (sot_path / "skills.yaml").write_text(
        "\n".join(
            [
                "skills:",
                "  - id: skill-1",
                "    name: Languages",
                "    keywords:",
                "      - Python",
            ]
        )
        + "\n"
    )
    (sot_path / "education.yaml").write_text(
        "\n".join(
            [
                "education:",
                "  - id: edu-1",
                "    institution: Example University",
                "    area: Computer Science",
            ]
        )
        + "\n"
    )
    (sot_path / "letters.yaml").write_text(
        "\n".join(
            [
                "letters:",
                "  - id: default-letter",
                "    title: Cover Letter",
                "    salutation: Dear Hiring Manager,",
                "    closing: Sincerely,",
                "    sections:",
                "      - id: intro",
                "        text: Intro text.",
                "        tags:",
                "          - general",
            ]
        )
        + "\n"
    )
