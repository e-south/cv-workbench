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

import pytest

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


def test_configuration_snapshot_is_immutable_and_independent_of_later_edits(tmp_path):
    from cvworkbench.config import read_config

    path = tmp_path / "workbench.yaml"
    path.write_text("paths:\n  dist: first\nlabels: [one, two]\n")
    snapshot = read_config(path)
    path.write_text("paths:\n  dist: second\n")

    assert resolve_dist_path(snapshot) == tmp_path / "first"
    assert resolve_dist_path(path) == tmp_path / "second"
    with pytest.raises(TypeError):
        snapshot.data["paths"]["dist"] = "third"
    assert snapshot.data["labels"] == ("one", "two")
    path.unlink()
    assert resolve_dist_path(snapshot) == tmp_path / "first"


def test_configuration_rejects_recursive_yaml_values(tmp_path):
    from cvworkbench.config import read_config

    path = tmp_path / "workbench.yaml"
    path.write_text("paths: &recursive\n  loop: *recursive\n")
    with pytest.raises(ValueError, match="recursive"):
        read_config(path)


def test_configuration_snapshot_requires_immutable_bytes_and_an_absolute_path(tmp_path):
    from cvworkbench.config import ConfigSnapshot

    with pytest.raises(TypeError, match="bytes"):
        ConfigSnapshot(path=tmp_path / "config.yaml", content=bytearray(b"paths: {}"))
    with pytest.raises(ValueError, match="absolute"):
        ConfigSnapshot(path=Path("config.yaml"), content=b"paths: {}")


@pytest.mark.parametrize(
    "key", ["dist", "publish", "runs", "registry", "drafts", "reviews", "projects"]
)
@pytest.mark.parametrize("value", [False, 123, [], ""])
def test_configured_artifact_paths_reject_non_string_or_empty_values(tmp_path, key, value):
    import yaml

    import cvworkbench.config as configuration

    path = tmp_path / "workbench.yaml"
    path.write_text(yaml.safe_dump({"paths": {key: value}}))
    resolver = getattr(configuration, f"resolve_{key}_path")
    with pytest.raises(ValueError, match=f"paths.{key}"):
        resolver(path)


def test_variant_retention_days_rejects_boolean(tmp_path):
    path = tmp_path / "workbench.yaml"
    path.write_text("variant_lifecycle:\n  ttl_days: true\n")
    with pytest.raises(ValueError, match="positive integer"):
        resolve_variant_ttl_days(path)


@pytest.mark.parametrize("content", [b"paths: [", b"\xff"])
def test_configuration_parse_errors_are_actionable_value_errors(tmp_path, content):
    from cvworkbench.config import read_config

    path = tmp_path / "workbench.yaml"
    path.write_bytes(content)
    with pytest.raises(ValueError, match="Config.*workbench.yaml"):
        read_config(path)


def test_configuration_aliases_preserve_sharing_without_mutating_the_snapshot(tmp_path):
    from cvworkbench.config import load_config, read_config

    path = tmp_path / "workbench.yaml"
    path.write_text(
        "paths: &paths\n  dist: first\n"
        "other_paths: *paths\n"
        "labels: &labels [one, two]\nother_labels: *labels\n"
    )
    snapshot = read_config(path)
    assert snapshot.data["paths"] is snapshot.data["other_paths"]
    assert snapshot.data["labels"] is snapshot.data["other_labels"]
    payload = load_config(snapshot)
    assert payload["paths"] is payload["other_paths"]
    assert payload["labels"] is payload["other_labels"]
    payload["paths"]["dist"] = "second"
    payload["labels"].append("three")
    assert resolve_dist_path(snapshot) == tmp_path / "first"
    assert snapshot.data["labels"] == ("one", "two")


@pytest.mark.parametrize("value", [True, 123, ["source"], {"source": "path"}])
def test_configured_source_path_requires_a_string(tmp_path, value):
    import yaml

    path = tmp_path / "workbench.yaml"
    path.write_text(yaml.safe_dump({"paths": {"sot": value}}))
    with pytest.raises(ValueError, match="paths.sot"):
        resolve_sot_path(None, path)


@pytest.mark.parametrize("key", ["pdf_engine", "style_preset"])
@pytest.mark.parametrize("value", [False, 123, [], ""])
def test_explicit_optional_render_settings_require_nonempty_strings(tmp_path, key, value):
    import yaml

    import cvworkbench.config as configuration

    path = tmp_path / "workbench.yaml"
    path.write_text(yaml.safe_dump({"render": {key: value}}))
    resolver = getattr(configuration, f"resolve_{key}")
    with pytest.raises(ValueError, match=f"render.{key}"):
        resolver(path)


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
