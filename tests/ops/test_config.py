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

from cvworkbench.config import (
    resolve_config_path,
    resolve_default_theme,
    resolve_dist_path,
    resolve_drafts_path,
    resolve_project_path,
    resolve_project_root,
    resolve_publish_path,
    resolve_reviews_path,
    resolve_runs_path,
    resolve_sot_path,
    resolve_themes_dir,
    resolve_variant_ttl_days,
)


def test_config_paths_resolve_relative_to_config_dir(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  sot: ../local/sot",
                "  dist: ../var/dist",
                "  publish: ../var/publish",
                "  runs: ../var/runs",
                "render:",
                "  themes_dir: ../build/themes",
                "  theme: default",
                "variants:",
                "  default: base",
            ]
        )
        + "\n"
    )

    assert resolve_sot_path(None, config_path) == (tmp_path / "local" / "sot").resolve()
    assert resolve_dist_path(config_path) == (tmp_path / "var" / "dist").resolve()
    assert resolve_publish_path(config_path) == (tmp_path / "var" / "publish").resolve()
    assert resolve_runs_path(config_path) == (tmp_path / "var" / "runs").resolve()
    assert resolve_themes_dir(config_path) == (tmp_path / "build" / "themes").resolve()
    assert resolve_default_theme(config_path) == "default"


def test_resolve_sot_path_uses_active_version(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "workbench.yaml"
    config_path.write_text("paths:\n  sot: ../local/sot\nvariants:\n  default: base\n")

    versions_root = tmp_path / "local" / "sot" / "versions" / "base"
    versions_root.mkdir(parents=True, exist_ok=True)
    active_file = tmp_path / "local" / "sot" / "ACTIVE"
    active_file.write_text("base\n")

    assert resolve_sot_path(None, config_path) == versions_root.resolve()


def test_resolve_config_path_searches_parent_dirs(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    config_dir = workspace / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "workbench.yaml"
    config_path.write_text("paths:\n  sot: ../local/sot\nvariants:\n  default: base\n")

    nested = workspace / "src" / "module"
    nested.mkdir(parents=True)

    monkeypatch.chdir(nested)

    resolved = resolve_config_path(Path("config/workbench.yaml"))

    assert resolved == config_path.resolve()


def test_project_paths_default_to_repo_root(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "workbench.yaml"
    config_path.write_text("paths:\n  sot: ../local/sot\nvariants:\n  default: base\n")

    assert resolve_project_root(config_path) == tmp_path.resolve()
    assert resolve_drafts_path(config_path) == (tmp_path / "var" / "drafts").resolve()
    assert resolve_reviews_path(config_path) == (tmp_path / "var" / "reviews").resolve()
    assert (
        resolve_project_path(Path("var/drafts/demo"), config_path)
        == (tmp_path / "var" / "drafts" / "demo").resolve()
    )


def test_resolve_variant_ttl_days(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "variant_lifecycle:",
                "  ttl_days: 7",
            ]
        )
        + "\n"
    )

    assert resolve_variant_ttl_days(config_path) == 7
