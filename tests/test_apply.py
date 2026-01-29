"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/test_apply.py

Tests applying draft patches to SoT.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import difflib
from pathlib import Path

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
