"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_input_provenance.py

Verify manifest fingerprints describe the bytes consumed while planning a build.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from cvworkbench.build.pipeline import execute_build
from cvworkbench.build.planning import plan_build
from cvworkbench.inputs.sot import load_sot, load_sot_snapshot
from cvworkbench.ops.scaffold import init_project


@pytest.fixture
def workspace(tmp_path):
    init_project(tmp_path, sample_default=True)
    source = tmp_path / "sot.sample"
    config = tmp_path / "config/workbench.yaml"
    variant = config.parent / "variants/base.yaml"
    person = yaml.safe_load((source / "person.yaml").read_text())
    person["name"] = "Captured Person"
    (source / "person.yaml").write_text(yaml.safe_dump(person))
    snippet = source / "snippets/captured.md"
    snippet.write_bytes(b"Captured summary.\r\nSecond line.\r\n")
    (source / "snippets.yaml").write_text(
        "snippets:\n  - id: captured-summary\n    scope: summary\n    path: snippets/captured.md\n"
    )
    return source, config, variant, snippet


@pytest.mark.parametrize("change", ["edit", "remove"])
@pytest.mark.parametrize("input_kind", ["source", "snippet", "variant"])
def test_manifest_uses_consumed_inputs_when_files_change_after_planning(
    workspace, change, input_kind
):
    source, config, variant, snippet = workspace
    path = {"source": source / "person.yaml", "snippet": snippet, "variant": variant}[input_kind]
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    plan = plan_build(sot_path=source, config_path=config, variant_id="base", formats=["md"])
    if change == "remove":
        path.unlink()
    elif input_kind == "source":
        data = yaml.safe_load(path.read_text())
        data["name"] = "Later Person"
        path.write_text(yaml.safe_dump(data))
    elif input_kind == "snippet":
        path.write_text("Later summary.\n")
    else:
        data = yaml.safe_load(path.read_text())
        data["variant"]["exclude_tags"] = ["core"]
        path.write_text(yaml.safe_dump(data))

    result = execute_build(plan)

    content = result.canonical_path.read_text()
    assert "Captured Person" in content
    assert "Captured summary." in content
    assert "Later Person" not in content
    assert "Later summary." not in content
    for directory in (result.dist_dir, result.run_dir):
        manifest = json.loads((directory / "manifest.json").read_text())
        if input_kind == "source":
            recorded = manifest["sot_hashes"]["person.yaml"]
        elif input_kind == "snippet":
            recorded = manifest["snippet_hashes"]["snippets/captured.md"]
        else:
            recorded = manifest["variant_hash"]
        assert recorded == original_hash


@pytest.mark.parametrize("change", ["add", "remove"])
def test_optional_inputs_are_reported_only_if_consumed(workspace, change):
    source, config, _, _ = workspace
    optional = source / "honors.yaml"
    original_hash = hashlib.sha256(optional.read_bytes()).hexdigest()
    if change == "add":
        optional.unlink()
    plan = plan_build(sot_path=source, config_path=config, variant_id="base", formats=["md"])
    if change == "add":
        optional.write_text("honors: []\n")
    else:
        optional.unlink()
    result = execute_build(plan)
    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    if change == "add":
        assert "honors.yaml" not in manifest["sot_hashes"]
    else:
        assert manifest["sot_hashes"]["honors.yaml"] == original_hash


@pytest.mark.parametrize("input_kind", ["source", "variant", "inline"])
def test_fingerprints_use_bytes_already_read_for_parsing(workspace, monkeypatch, input_kind):
    source, config, variant, _ = workspace
    inline = "  Captured inline summary.\n"
    if input_kind == "inline":
        (source / "snippets.yaml").write_text(
            yaml.safe_dump({"snippets": [{"id": "captured", "scope": "summary", "text": inline}]})
        )
    path = {
        "source": source / "person.yaml",
        "variant": variant,
        "inline": source / "snippets.yaml",
    }[input_kind]
    captured = path.read_bytes()
    parse = yaml.safe_load
    edits = []

    def edit_after_read(content):
        if content == captured.decode("utf-8"):
            path.write_text("changed: true\n")
            edits.append(path)
        return parse(content)

    monkeypatch.setattr(yaml, "safe_load", edit_after_read)
    plan = plan_build(sot_path=source, config_path=config, variant_id="base", formats=["md"])
    result = execute_build(plan)
    manifest = json.loads((result.run_dir / "manifest.json").read_text())

    assert edits == [path]
    assert "Captured Person" in result.canonical_path.read_text()
    expected = hashlib.sha256(captured).hexdigest()
    if input_kind == "variant":
        assert manifest["variant_hash"] == expected
    else:
        assert manifest["sot_hashes"][path.name] == expected
    if input_kind == "inline":
        assert manifest["snippet_hashes"] == {
            "inline:captured": hashlib.sha256(inline.encode("utf-8")).hexdigest()
        }
        assert "Captured inline summary." in result.canonical_path.read_text()


def test_repeated_snippet_path_uses_one_captured_content(workspace, monkeypatch):
    source, _, _, snippet = workspace
    (source / "snippets.yaml").write_text(
        yaml.safe_dump(
            {"snippets": [{"id": name, "path": "snippets/captured.md"} for name in ("a", "b")]}
        )
    )
    captured = snippet.read_bytes()
    read_bytes = Path.read_bytes
    reads = []

    def edit_after_read(path):
        content = read_bytes(path)
        if path == snippet:
            reads.append(path)
            path.write_bytes(b"Later summary.\n")
        return content

    monkeypatch.setattr(Path, "read_bytes", edit_after_read)
    snapshot = load_sot_snapshot(source)

    assert reads == [snippet]
    assert [entry["text"] for entry in snapshot.data["snippets"]["snippets"]] == [
        "Captured summary.\nSecond line.",
        "Captured summary.\nSecond line.",
    ]
    assert snapshot.snippet_hashes == {"snippets/captured.md": hashlib.sha256(captured).hexdigest()}


def test_source_snapshot_preserves_payload_and_stable_byte_hashes(workspace):
    source, _, _, snippet = workspace
    expected = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in source.glob("*.yaml")
    }
    snapshot = load_sot_snapshot(source)

    assert snapshot.data == load_sot(source)
    assert snapshot.sot_hashes == expected
    assert snapshot.snippet_hashes == {
        "snippets/captured.md": hashlib.sha256(snippet.read_bytes()).hexdigest()
    }
    assert "Captured Person" not in repr(snapshot)
    assert "Captured summary" not in repr(snapshot)
    with pytest.raises(TypeError):
        snapshot.sot_hashes["person.yaml"] = "different"
    with pytest.raises(TypeError):
        snapshot.snippet_hashes["snippets/captured.md"] = "different"
