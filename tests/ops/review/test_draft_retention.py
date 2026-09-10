"""Keep import comparison runs independently of recency and artifact health."""

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.ops.runs import RunError, gc_runs
from tests.ops.test_runs_gc import _write_config, _write_run


def _workspace(root, *, project=False, status="ready", custom_root=False):
    config = _write_config(root)
    prefix = "projects/example/" if project else ""
    source = _write_run(root, prefix + "source", "2026-01-01T00:00:00+00:00", "base")
    newest = _write_run(root, prefix + "current", "2026-01-03T00:00:00+00:00", "base")
    unrelated = _write_run(root, prefix + "unneeded", "2026-01-02T00:00:00+00:00", "base")
    canonical = source / "canonical.md"
    canonical.write_text("Original comparison baseline.\n")
    drafts = root / "var" / ("custom-drafts" if custom_root else "drafts")
    if custom_root:
        data = yaml.safe_load(config.read_text())
        data["paths"]["drafts"] = "../var/custom-drafts"
        config.write_text(yaml.safe_dump(data))
    draft = drafts / "import-example"
    draft.mkdir(parents=True)
    (draft / "draft.json").write_text(
        json.dumps(
            {
                "source": "import-docx",
                "created_at": "2026-01-02T12:00:00+00:00",
                "run_id": prefix + "source",
                "variant_id": "base",
                "review_dir": str(root / "var/reviews/base"),
                "canonical_path": str(canonical),
                "canonical_hash": hashlib.sha256(canonical.read_bytes()).hexdigest(),
                "imported_path": str(draft / "imported.md"),
                "patch_path": "patch.yaml",
                "apply_status": status,
            }
        )
    )
    (draft / "imported.md").write_text("Reviewed document.\n")
    return config, source, newest, unrelated, draft


def _gc(config, *, confirm=False):
    return gc_runs(
        config_path=config, keep_latest=1, keep=[], include_invalid=True, confirm=confirm
    )


def _contents(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("project", [False, True])
@pytest.mark.parametrize("status", ["ready", "ready_no_changes", "review_diff_only"])
def test_import_draft_retains_source_and_explains_it(tmp_path, project, status):
    config, source, newest, unrelated, draft = _workspace(tmp_path, project=project, status=status)
    before = _contents(tmp_path)

    plan = _gc(config)

    assert [item.path for item in plan.candidates] == [unrelated]
    assert plan.keep_reasons[source.relative_to(tmp_path / "var/runs").as_posix()] == [
        "draft:import-example"
    ]
    assert _contents(tmp_path) == before
    draft_before = _contents(draft)
    result = _gc(config, confirm=True)
    assert result.removed == 1
    assert source.is_dir() and newest.is_dir() and not unrelated.exists()
    assert _contents(draft) == draft_before


@pytest.mark.parametrize("damage", ["manifest", "missing-canonical", "changed-canonical"])
def test_damaged_import_baseline_is_retained_for_recovery(tmp_path, damage):
    config, source, _, unrelated, _ = _workspace(tmp_path, project=True)
    if damage == "manifest":
        (source / "manifest.json").write_text("invalid")
    elif damage == "missing-canonical":
        (source / "canonical.md").unlink()
    else:
        (source / "canonical.md").write_text("Independently changed baseline.")

    result = _gc(config, confirm=True)

    assert result.removed == 1
    assert source.is_dir() and not unrelated.exists()
    assert result.keep_reasons["projects/example/source"] == ["draft:import-example"]


def test_cli_plan_uses_configured_draft_store(tmp_path):
    config, source, _, unrelated, _ = _workspace(tmp_path, custom_root=True)
    before = _contents(tmp_path)

    result = CliRunner().invoke(app, ["runs", "gc", "--config", str(config), "--json"])

    assert result.exit_code == 2, result.output
    data = json.loads(result.stdout)
    assert data["keep_reasons"]["source"] == ["draft:import-example"]
    assert [item["path"] for item in data["candidates"]] == [str(unrelated)]
    assert source.is_dir() and _contents(tmp_path) == before


def test_external_baseline_does_not_retain_an_unrelated_same_id_run(tmp_path):
    config, source, newest, unrelated, draft = _workspace(tmp_path)
    external = tmp_path / "external/source/canonical.md"
    external.parent.mkdir(parents=True)
    external.write_text("External comparison baseline.\n")
    path = draft / "draft.json"
    data = json.loads(path.read_text())
    data["canonical_path"] = str(external)
    path.write_text(json.dumps(data))

    result = _gc(config, confirm=True)

    assert result.removed == 2
    assert not source.exists() and not unrelated.exists()
    assert newest.is_dir() and external.read_text() == "External comparison baseline.\n"
    assert "source" not in result.keep_reasons


@pytest.mark.parametrize(
    "damage",
    [
        "invalid-json",
        "unknown-kind",
        "absolute-id",
        "traversal-id",
        "relative-path",
        "wrong-filename",
        "path-id-disagreement",
        "missing-record",
        "empty-import",
        "duplicate-field",
        "symlink-record",
        "symlink-directory",
    ],
)
def test_ambiguous_import_identity_stops_before_deletion(tmp_path, damage):
    config, source, _, unrelated, draft = _workspace(tmp_path)
    path = draft / "draft.json"
    data = json.loads(path.read_text())
    if damage == "invalid-json":
        path.write_text("{")
    elif damage == "missing-record":
        path.unlink()
    elif damage == "empty-import":
        path.unlink()
        (draft / "imported.md").unlink()
    elif damage == "duplicate-field":
        path.write_text(path.read_text()[:-1] + ', "run_id": "source"}')
    elif damage == "symlink-record":
        external = tmp_path / "external.json"
        path.rename(external)
        path.symlink_to(external)
    elif damage == "symlink-directory":
        external = tmp_path / "external-draft"
        draft.rename(external)
        draft.symlink_to(external, target_is_directory=True)
    else:
        field, value = {
            "unknown-kind": ("source", "unknown-import"),
            "absolute-id": ("run_id", str(source)),
            "traversal-id": ("run_id", "../source"),
            "relative-path": ("canonical_path", "source/canonical.md"),
            "wrong-filename": ("canonical_path", str(source / "other.md")),
            "path-id-disagreement": ("run_id", "current"),
        }[damage]
        data[field] = value
        path.write_text(json.dumps(data))
    before = _contents(tmp_path)

    with pytest.raises(RunError, match="[Ii]mport draft"):
        _gc(config, confirm=True)

    assert source.is_dir() and unrelated.is_dir()
    assert _contents(tmp_path) == before


@pytest.mark.parametrize("entrypoint", ["api", "cli"])
def test_gc_keeps_one_configuration_generation(tmp_path, monkeypatch, entrypoint):
    config, source, _, unrelated, _ = _workspace(tmp_path)
    read_bytes = Path.read_bytes

    def change_after_read(path):
        content = read_bytes(path)
        if path == config:
            data = yaml.safe_load(content)
            data["paths"]["drafts"] = "../var/other-drafts"
            path.write_text(yaml.safe_dump(data))
        return content

    monkeypatch.setattr(Path, "read_bytes", change_after_read)
    if entrypoint == "api":
        result = _gc(config, confirm=True)
        assert result.removed == 1
    else:
        result = CliRunner().invoke(app, ["runs", "gc", "--config", str(config), "--yes", "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["removed"] == 1

    assert source.is_dir() and not unrelated.exists()
