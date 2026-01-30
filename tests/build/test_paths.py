"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_paths.py

Tests build path resolution helpers.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from cvworkbench.build.paths import filters_dir, output_path
from cvworkbench.variants import Variant


def test_filters_dir_exists() -> None:
    path = filters_dir()

    assert path.exists()
    assert (path / "select.lua").exists()


def test_output_path_ats_extension() -> None:
    variant = Variant(
        id="base",
        include_tags=[],
        exclude_tags=[],
        max_bullets_per_role=None,
        order=[],
        outputs=["md"],
        output_name="cv",
        document_type="resume",
        letter_id=None,
        render_theme=None,
        render_style_preset=None,
    )

    path = output_path(Path("dist"), variant, "ats")

    assert path.name == "cv.ats.txt"
