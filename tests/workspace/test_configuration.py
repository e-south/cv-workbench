"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/workspace/test_configuration.py

Tests configuration identity across workspace inventories and workflow guidance.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from cvworkbench.build.pipeline import build_documents
from cvworkbench.cli import app
from cvworkbench.config import read_config
from cvworkbench.ops.projects import create_project_from_file
from cvworkbench.ops.scaffold import init_project
from cvworkbench.workspace.context import inspect_workspace


def _populated_workspace(root: Path) -> Path:
    init_project(root, sample_default=True)
    config = root / "config/workbench.yaml"
    build_documents(
        sot_path=root / "sot.sample", config_path=config, variant_id="base", formats=["md"]
    )
    job = root / "job.txt"
    job.write_text("Research scientist with Python and engineering experience.\n")
    create_project_from_file(
        job_path=job,
        slug="research",
        base_variant_id="base",
        config_path=config,
        sot_path=root / "sot.sample",
        store_raw=False,
    )
    review = root / "var/reviews/base"
    review.mkdir(parents=True)
    (review / "review.md").write_text("Content review awaiting document exports.\n")
    publication = root / "var/publish/base"
    publication.mkdir(parents=True)
    (publication / "note.txt").write_text("Publication awaiting preparation.\n")
    (config.parent / "site-sync.yaml").write_text("site:\n  publish_variant: base\n")
    return config


@pytest.mark.parametrize("entrypoint", ["api", "context", "bootstrap", "workflow", "status"])
@pytest.mark.parametrize("mutation", ["edit", "remove"])
def test_inspection_uses_one_configuration_generation(tmp_path, monkeypatch, entrypoint, mutation):
    config = _populated_workspace(tmp_path)

    def inspect():
        if entrypoint == "api":
            return inspect_workspace(config=config, sot_path=None, strict=False)
        result = CliRunner().invoke(app, [entrypoint, "--config", str(config), "--json"])
        assert result.exit_code == 0, result.output
        return json.loads(result.stdout)

    expected = inspect()
    changed = yaml.safe_load(config.read_text())
    changed["project"]["name"] = "Different workspace settings"
    changed["variants"]["default"] = "cover-letter"
    changed["variant_lifecycle"]["ttl_days"] = 99
    for key in ("sot", "runs", "projects", "reviews", "publish"):
        changed["paths"][key] = f"../different/{key}"
    original_read = Path.read_bytes
    reads = []

    def mutate_after_read(path):
        content = original_read(path)
        if path == config:
            reads.append(path)
            if mutation == "edit":
                path.write_text(yaml.safe_dump(changed))
            else:
                path.unlink()
        return content

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", mutate_after_read)
        observed = inspect()
    assert observed == expected
    assert reads == [config]
    if mutation == "edit":
        refreshed = inspect_workspace(config=config, sot_path=None, strict=False)
        assert refreshed["sot"]["status"] == "missing"
        assert refreshed["variants"]["default"] == "cover-letter"
        assert refreshed["projects"]["count"] == 0


def test_inspection_accepts_an_explicit_configuration_snapshot(tmp_path):
    config = _populated_workspace(tmp_path)
    expected = inspect_workspace(config=config, sot_path=None, strict=True)
    snapshot = read_config(config)
    config.unlink()
    assert inspect_workspace(config=snapshot, sot_path=None, strict=True) == expected


def test_missing_source_guidance_uses_captured_workspace_location(tmp_path, monkeypatch):
    init_project(tmp_path, sample_default=True)
    config = tmp_path / "config/workbench.yaml"
    data = yaml.safe_load(config.read_text())
    data["paths"]["sot"] = "../missing"
    config.write_text(yaml.safe_dump(data))
    expected = inspect_workspace(config=config, sot_path=None, strict=False)
    assert expected["recipes"][0]["id"] == "bootstrap.sample_workspace"
    original_read = Path.read_bytes

    def remove_after_read(path):
        content = original_read(path)
        if path == config:
            path.unlink()
        return content

    monkeypatch.setattr(Path, "read_bytes", remove_after_read)
    assert inspect_workspace(config=config, sot_path=None, strict=False) == expected
