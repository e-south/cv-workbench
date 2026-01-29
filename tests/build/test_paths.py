"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_paths.py

Tests build path resolution helpers.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from cvworkbench.build.paths import filters_dir


def test_filters_dir_exists() -> None:
    path = filters_dir()

    assert path.exists()
    assert (path / "select.lua").exists()
