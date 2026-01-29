"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_validation.py

Tests strict schema validation for SoT inputs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from cvworkbench.inputs.validation import validate_sot


def test_validate_rejects_unknown_fields(tmp_path: Path) -> None:
    _write_minimal_sot(tmp_path, extra_person_field=True)

    errors = validate_sot(tmp_path)

    assert errors
    assert any("person.extra" in error for error in errors)


def test_validate_rejects_invalid_optional_files(tmp_path: Path) -> None:
    _write_minimal_sot(tmp_path, extra_person_field=False)

    (tmp_path / "publications.yaml").write_text(
        "\n".join(
            [
                "publications:",
                "  - id: pub-1",
                "    title: Example publication",
            ]
        )
        + "\n"
    )

    errors = validate_sot(tmp_path)

    assert errors
    assert any("publications" in error for error in errors)


def test_validate_rejects_invalid_snippet(tmp_path: Path) -> None:
    _write_minimal_sot(tmp_path, extra_person_field=False)

    (tmp_path / "snippets.yaml").write_text(
        "\n".join(
            [
                "snippets:",
                "  - id: summary",
                "    scope: summary",
            ]
        )
        + "\n"
    )

    errors = validate_sot(tmp_path)

    assert errors
    assert any("snippets" in error for error in errors)


def test_validate_rejects_missing_snippet_path(tmp_path: Path) -> None:
    _write_minimal_sot(tmp_path, extra_person_field=False)

    (tmp_path / "snippets.yaml").write_text(
        "\n".join(
            [
                "snippets:",
                "  - id: summary",
                "    scope: summary",
                "    path: snippets/missing.md",
            ]
        )
        + "\n"
    )

    errors = validate_sot(tmp_path)

    assert errors
    assert any("snippets" in error for error in errors)


def _write_minimal_sot(tmp_path: Path, *, extra_person_field: bool) -> None:
    person_lines = [
        "id: sample",
        "name: Sample User",
    ]
    if extra_person_field:
        person_lines.append("extra: nope")
    (tmp_path / "person.yaml").write_text("\n".join(person_lines) + "\n")

    (tmp_path / "experience.yaml").write_text(
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

    (tmp_path / "projects.yaml").write_text(
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

    (tmp_path / "skills.yaml").write_text(
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

    (tmp_path / "education.yaml").write_text(
        "\n".join(
            [
                "education:",
                "  - id: edu-1",
                "    institution: Example University",
                "    area: Computer Science",
                "    tags:",
                "      - domain:education",
            ]
        )
        + "\n"
    )

    (tmp_path / "letters.yaml").write_text(
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
