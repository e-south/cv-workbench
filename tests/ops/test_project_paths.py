"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_project_paths.py

Tests project path resolution defaults.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from cvworkbench.config import resolve_projects_path


def test_resolve_projects_path_default(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "workbench.yaml"
    config_path.write_text("paths: {}\n")

    resolved = resolve_projects_path(config_path)

    assert resolved == tmp_path / "projects"
