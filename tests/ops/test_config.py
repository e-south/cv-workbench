"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_config.py

Tests configuration path resolution.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from cvworkbench.config import resolve_config_path, resolve_dist_path, resolve_runs_path, resolve_sot_path


def test_config_paths_resolve_relative_to_config_dir(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  sot: ../sot",
                "  dist: ../dist",
                "  runs: ../runs",
                "variants:",
                "  default: base",
            ]
        )
        + "\n"
    )

    assert resolve_sot_path(None, config_path) == (tmp_path / "sot").resolve()
    assert resolve_dist_path(config_path) == (tmp_path / "dist").resolve()
    assert resolve_runs_path(config_path) == (tmp_path / "runs").resolve()


def test_resolve_config_path_searches_parent_dirs(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    config_dir = workspace / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "workbench.yaml"
    config_path.write_text("paths:\n  sot: ../sot\nvariants:\n  default: base\n")

    nested = workspace / "src" / "module"
    nested.mkdir(parents=True)

    monkeypatch.chdir(nested)

    resolved = resolve_config_path(Path("config/workbench.yaml"))

    assert resolved == config_path.resolve()
