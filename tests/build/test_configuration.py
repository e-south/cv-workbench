"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_configuration.py

Tests coherent configuration selection across complete build operations.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cvworkbench.build import pipeline
from cvworkbench.cli import app
from cvworkbench.ops.scaffold import init_project
from cvworkbench.themes import ThemeError


def test_build_uses_one_configuration_generation(tmp_path: Path, monkeypatch) -> None:
    init_project(tmp_path, sample_default=True)
    config = tmp_path / "config/workbench.yaml"
    initial = config.read_text()
    changed = initial.replace("dist: ../var/dist", "dist: ../another-dist").replace(
        "theme: default", "theme: absent-theme"
    )
    assert changed != initial
    original_markdown = pipeline.build_markdown

    def change_config_during_build(*args, **kwargs):
        markdown = original_markdown(*args, **kwargs)
        config.write_text(changed)
        return markdown

    monkeypatch.setattr(pipeline, "build_markdown", change_config_during_build)
    result = pipeline.build_documents(
        sot_path=tmp_path / "sot.sample", config_path=config, variant_id=None, formats=["md"]
    )

    assert result.theme_id == "default"
    assert result.dist_dir == tmp_path / "var/dist/base"
    assert (result.dist_dir / "cv.md").is_file()
    assert not (tmp_path / "another-dist").exists()
    for directory in (result.dist_dir, result.run_dir):
        manifest = json.loads((directory / "manifest.json").read_text())
        assert manifest["configuration"]["sha256"] == hashlib.sha256(initial.encode()).hexdigest()


@pytest.mark.parametrize("command", ["build", "render"])
def test_cli_captures_config_once_before_selecting_inputs(tmp_path, monkeypatch, command):
    init_project(tmp_path, sample_default=True)
    config = tmp_path / "config/workbench.yaml"
    initial = config.read_text()
    changed = initial.replace("dist: ../var/dist", "dist: ../another-dist").replace(
        "theme: default", "theme: absent-theme"
    )
    original_read = Path.read_bytes
    reads = []

    def change_after_read(path):
        content = original_read(path)
        if path == config:
            reads.append(path)
            path.write_text(changed)
        return content

    monkeypatch.setattr(Path, "read_bytes", change_after_read)
    args = [command, "--config", str(config), "--format", "md"]
    if command == "render":
        canonical = tmp_path / "input.md"
        canonical.write_text("# Example\n\nResearch and engineering.\n")
        args += ["--canonical", str(canonical)]
    result = CliRunner().invoke(app, args)

    assert result.exit_code == 0, result.output
    assert reads == [config]
    assert (tmp_path / "var/dist/base/cv.md").is_file()
    assert not (tmp_path / "another-dist").exists()


@pytest.mark.parametrize("field", ["theme", "style_preset", "themes_dir"])
@pytest.mark.parametrize("entrypoint", ["api", "build", "render"])
def test_invalid_render_configuration_fails_before_build_writes(tmp_path, field, entrypoint):
    import yaml

    init_project(tmp_path, sample_default=True)
    config = tmp_path / "config/workbench.yaml"
    data = yaml.safe_load(config.read_text())
    data["render"][field] = "absent-value"
    config.write_text(yaml.safe_dump(data))
    canonical = tmp_path / "input.md"
    canonical.write_text("# Example\n")
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}

    if entrypoint == "api":
        with pytest.raises((ValueError, ThemeError), match="not found|Unknown|unknown"):
            pipeline.build_documents(
                sot_path=tmp_path / "sot.sample",
                config_path=config,
                variant_id=None,
                formats=["pdf"],
            )
    else:
        args = [entrypoint, "--config", str(config), "--format", "pdf"]
        if entrypoint == "render":
            args += ["--canonical", str(canonical)]
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 1
        assert "not found" in result.output
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} == before


def test_invalid_output_path_fails_before_creating_a_run(tmp_path):
    import yaml

    init_project(tmp_path, sample_default=True)
    config = tmp_path / "config/workbench.yaml"
    data = yaml.safe_load(config.read_text())
    data["paths"]["dist"] = 42
    config.write_text(yaml.safe_dump(data))
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}

    result = CliRunner().invoke(app, ["build", "--config", str(config), "--format", "md"])

    assert result.exit_code == 1
    assert "paths.dist" in result.output
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} == before
