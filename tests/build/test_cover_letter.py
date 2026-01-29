"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_cover_letter.py

Tests cover letter rendering and tag filtering.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from cvworkbench.build.pipeline import build_documents


def test_cover_letter_renders_sections() -> None:
    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=Path("config/workbench.yaml"),
        variant_id="cover-letter",
        formats=["md"],
    )

    output_path = result.dist_dir / "cover-letter.md"
    content = output_path.read_text()

    assert "Dear Hiring Manager" in content
    assert "Systems with clear ownership" in content
    assert "Sincerely," in content


def test_cover_letter_tag_filters_sections() -> None:
    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=Path("config/workbench.yaml"),
        variant_id="cover-letter-focused",
        formats=["md"],
    )

    output_path = result.dist_dir / "cover-letter.md"
    content = output_path.read_text()

    assert "Systems with clear ownership" in content
    assert "Hands-on incident response" not in content


def test_cover_letter_includes_snippet_open_close() -> None:
    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=Path("config/workbench.yaml"),
        variant_id="cover-letter",
        formats=["md"],
    )

    output_path = result.dist_dir / "cover-letter.md"
    content = output_path.read_text()

    assert "I value teams that pair curiosity with execution." in content
    assert "Thank you for your consideration." in content
