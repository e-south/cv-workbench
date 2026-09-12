"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_render_assets.py

Verify planned render assets remain stable until a complete build commits.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import hashlib
import json
import shutil
from dataclasses import replace

import pytest
import yaml

from cvworkbench.build import artifacts, planning
from cvworkbench.build.pipeline import execute_build
from cvworkbench.build.rendering import (
    RenderError,
    RenderRequest,
    render_document,
    render_documents,
)
from cvworkbench.variants import load_variant


@pytest.fixture
def render_workspace(sample_workspace, monkeypatch):
    root = sample_workspace
    filters = root / "filters"
    shutil.copytree(planning.filters_dir(), filters)
    monkeypatch.setattr(planning, "filters_dir", lambda: filters)
    theme = root / "build/themes/default"
    template = theme / "templates/html.html"
    template.parent.mkdir()
    template.write_text("<html><head><title>CV</title></head><body>$body$</body></html>\n")
    definition = theme / "theme.yaml"
    data = yaml.safe_load(definition.read_text())
    data["routes"]["html_preview"]["template"] = "templates/html.html"
    definition.write_text(yaml.safe_dump(data, sort_keys=False))
    paths = {
        "theme": definition,
        "template": template,
        "defaults": theme / "pandoc/html.defaults.yaml",
        "style": theme / "styles/html/modern.css",
        "filter": next(filters.glob("*.lua")),
        "filter_support": filters / "metadata.lua",
    }
    return root, paths


def _plan(root):
    return planning.plan_build(
        sot_path=root / "sot.sample",
        config_path=root / "config/workbench.yaml",
        variant_id="base",
        formats=["html"],
    )


def _files(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    "asset", ["theme", "template", "defaults", "style", "filter", "filter_support"]
)
@pytest.mark.parametrize("change", ["edit", "remove"])
def test_stale_render_asset_fails_before_output_allocation(
    render_workspace, tmp_path, asset, change
):
    root, paths = render_workspace
    plan = _plan(root)
    path = paths[asset]
    if change == "edit":
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        path.unlink()
    with pytest.raises(ValueError, match="Render asset"):
        execute_build(plan, run_dir=tmp_path / "run", dist_dir=tmp_path / "dist")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("asset", ["template", "defaults", "style", "filter", "filter_support"])
def test_asset_edit_during_real_render_preserves_the_previous_bundle(
    render_workspace, tmp_path, monkeypatch, asset
):
    root, paths = render_workspace
    run, dist = tmp_path / "run", tmp_path / "dist"
    execute_build(_plan(root), run_dir=run, dist_dir=dist)
    before = _files(tmp_path)
    plan = _plan(root)
    render = artifacts.render_documents

    def edit_after_render(*args, **kwargs):
        result = render(*args, **kwargs)
        path = paths[asset]
        path.write_bytes(path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(artifacts, "render_documents", edit_after_render)
    with pytest.raises(ValueError, match="Render asset"):
        execute_build(plan, run_dir=run, dist_dir=dist)
    assert _files(tmp_path) == before


def test_theme_edit_after_parsing_is_rejected_during_planning(render_workspace, monkeypatch):
    root, paths = render_workspace
    parse = yaml.safe_load
    observed = []

    def edit_after_parse(content):
        data = parse(content)
        if isinstance(data, dict) and data.get("id") == "default" and "routes" in data:
            observed.append(True)
            path = paths["theme"]
            path.write_bytes(path.read_bytes() + b"\n")
        return data

    monkeypatch.setattr(yaml, "safe_load", edit_after_parse)
    with pytest.raises(ValueError, match="Render asset"):
        _plan(root)
    assert observed == [True]


@pytest.mark.parametrize("entrypoint", ["single", "batch"])
def test_explicit_empty_filter_list_disables_discovery(sample_workspace, tmp_path, entrypoint):
    source = tmp_path / "input.md"
    source.write_text("# Example\n\nKeep this text.\n")
    filters = tmp_path / "filters"
    filters.mkdir()
    (filters / "select.lua").write_text('function Pandoc(doc) error("unexpected filter") end\n')
    variant = load_variant(sample_workspace / "config/variants/base.yaml")
    target = tmp_path / "output.md"
    request = RenderRequest(source, target, variant, filters, "md", None)
    if entrypoint == "single":
        render_document(source, target, variant, filters, "md", None, filter_paths=[])
    else:
        render_documents([request], filter_paths=[])
    assert "Keep this text." in target.read_text()
    with pytest.raises(RenderError, match="unexpected filter"):
        render_documents([request])


@pytest.mark.parametrize("change", ["template", "defaults", "style_hash", "filter_selection"])
def test_changed_render_selection_requires_a_new_asset_contract(render_workspace, tmp_path, change):
    root, _ = render_workspace
    plan = _plan(root)
    if change == "filter_selection":
        plan = replace(plan, filter_paths=())
    else:
        route = plan.render_plans["html"]
        if change == "style_hash":
            route = replace(route, style_hash="0" * 64)
        else:
            path = root / ("another.html" if change == "template" else "another.yaml")
            path.write_text("$body$" if change == "template" else "standalone: true\n")
            route = replace(route, **{change: path if change == "template" else [path]})
        plan = replace(plan, render_plans={"html": route})
    with pytest.raises(ValueError, match="Render asset"):
        execute_build(plan, run_dir=tmp_path / "run", dist_dir=tmp_path / "dist")
    assert not list(tmp_path.iterdir())


def test_manifest_records_ordered_selected_filter_fingerprints(render_workspace, tmp_path):
    root, _ = render_workspace
    plan = _plan(root)
    result = execute_build(plan, run_dir=tmp_path / "run", dist_dir=tmp_path / "dist")
    expected = [
        {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in plan.filter_paths
    ]
    support = root / "filters/metadata.lua"
    expected.append(
        {"name": "metadata.lua", "sha256": hashlib.sha256(support.read_bytes()).hexdigest()}
    )
    for directory in (result.run_dir, result.dist_dir):
        manifest = json.loads((directory / "manifest.json").read_text())
        assert manifest["render"]["filters"] == expected
        assert str(root) not in json.dumps(manifest["render"]["filters"])


def test_empty_planned_filters_do_not_pick_up_later_files(render_workspace, tmp_path):
    root, _ = render_workspace
    for path in (root / "filters").glob("*.lua"):
        path.unlink()
    plan = _plan(root)
    (root / "filters/select.lua").write_text(
        'function Pandoc(doc) error("unexpected late filter") end\n'
    )
    result = execute_build(plan, run_dir=tmp_path / "run", dist_dir=tmp_path / "dist")
    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    assert manifest["render"]["filters"] == []
    assert (result.dist_dir / "cv.html").is_file()
