"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/review/test_provenance.py

Tests durable source identity for editable review bundles.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

import cvworkbench.storage as atomic
from cvworkbench.cli import app
from cvworkbench.ops.review import ReviewError
from cvworkbench.ops.review.catalog import list_review_summaries
from cvworkbench.ops.review.importing import import_docx_review
from cvworkbench.ops.review.packs import build_review_pack
from cvworkbench.ops.review.record import load_source_record
from cvworkbench.ops.runs import RunError, gc_runs
from tests.ops.test_review import (
    _write_minimal_config,
    _write_project_manifest,
    _write_run_manifest_at,
)


def _review_workspace(root: Path):
    config = _write_minimal_config(root)
    run = root / "var" / "runs" / "source"
    _write_run_manifest_at(
        run, variant_id="base", canonical="Original baseline.\n", review_ready=True
    )
    pack = build_review_pack(config_path=config, variant_id=None, run="source")
    return config, run, pack


def test_review_pack_records_exact_source_artifacts(tmp_path: Path) -> None:
    _, run, pack = _review_workspace(tmp_path)

    record = json.loads(pack.source_record_path.read_text())
    assert record["schema_version"] == 1
    assert record["kind"] == "content-review"
    assert record["run_id"] == "source"
    assert record["run_path"] == str(run)
    assert record["files"]["canonical.md"] == hashlib.sha256(b"Original baseline.\n").hexdigest()
    assert set(record["files"]) == {
        "canonical.md",
        "selection.json",
        "manifest.json",
        "cv.docx",
        "cv.pdf",
    }
    assert record["docx_name"] == pack.docx_path.name
    assert record["pdf_name"] == pack.pdf_path.name
    assert pack.source_record_path.stat().st_mode & 0o777 == 0o600


def _write_edited_docx(path: Path) -> None:
    subprocess.run(
        ["pandoc", "--from", "markdown", "--to", "docx", "--output", str(path)],
        input="Edited copy.\n",
        text=True,
        capture_output=True,
        check=True,
    )


def test_import_uses_bundle_source_after_a_newer_build(tmp_path: Path) -> None:
    config, run, pack = _review_workspace(tmp_path)
    newer = run.parent / "newer"
    _write_run_manifest_at(
        newer, variant_id="base", canonical="Newer baseline.\n", review_ready=True
    )
    manifest = json.loads((newer / "manifest.json").read_text())
    manifest["created_at"] = "2026-01-02T00:00:00+00:00"
    (newer / "manifest.json").write_text(json.dumps(manifest))
    _write_edited_docx(pack.docx_path)

    result = import_docx_review(
        docx_path=pack.docx_path,
        config_path=config,
        run=None,
        variant_id="base",
        project_dir=None,
    )

    assert result.run_id == "source"
    assert "Original baseline." in result.patch_path.read_text()
    assert "Newer baseline." not in result.patch_path.read_text()
    assert "Edited copy." in result.patch_path.read_text()


def test_import_rejects_run_conflicting_with_bundle_source(tmp_path: Path) -> None:
    config, run, pack = _review_workspace(tmp_path)
    _write_run_manifest_at(
        run.parent / "other", variant_id="base", canonical="Other.\n", review_ready=True
    )
    _write_edited_docx(pack.docx_path)

    with pytest.raises(ReviewError, match="conflicts with review source"):
        import_docx_review(
            docx_path=pack.docx_path,
            config_path=config,
            run="other",
            variant_id=None,
            project_dir=None,
        )
    assert not (tmp_path / "var" / "drafts").exists()


def test_import_rejects_changed_baseline_before_writing(tmp_path: Path) -> None:
    config, run, pack = _review_workspace(tmp_path)
    (run / "canonical.md").write_text("Changed baseline.\n")
    _write_edited_docx(pack.docx_path)

    with pytest.raises(ReviewError, match="source artifact changed"):
        import_docx_review(
            docx_path=pack.docx_path,
            config_path=config,
            run=None,
            variant_id="base",
            project_dir=None,
        )
    assert not (tmp_path / "var" / "drafts").exists()


@pytest.mark.parametrize("damaged_manifest", [False, True])
def test_gc_retains_review_source_even_if_manifest_is_damaged(
    tmp_path: Path, damaged_manifest: bool
) -> None:
    config, run, _ = _review_workspace(tmp_path)
    other = run.parent / "unneeded"
    _write_run_manifest_at(other, variant_id="base", canonical="Other.\n", review_ready=True)
    if damaged_manifest:
        (run / "manifest.json").write_text("damaged")

    result = gc_runs(config_path=config, keep_latest=0, keep=[], include_invalid=True, confirm=True)

    assert run.is_dir()
    assert not other.exists()
    assert result.removed == 1
    assert result.keep_reasons["source"] == ["review:base"]


def test_gc_rejects_unreadable_review_identity_before_deletion(tmp_path: Path) -> None:
    config, run, pack = _review_workspace(tmp_path)
    pack.source_record_path.write_text("{")

    with pytest.raises(RunError, match="review source record"):
        gc_runs(config_path=config, keep_latest=0, keep=[], include_invalid=True, confirm=True)
    assert run.is_dir()


def test_import_without_source_record_requires_explicit_run(tmp_path: Path) -> None:
    config, _, pack = _review_workspace(tmp_path)
    pack.source_record_path.unlink()
    _write_edited_docx(pack.docx_path)

    with pytest.raises(ReviewError, match="requires an explicit --run"):
        import_docx_review(
            docx_path=pack.docx_path,
            config_path=config,
            run=None,
            variant_id="base",
            project_dir=None,
        )
    assert not (tmp_path / "var" / "drafts").exists()
    result = import_docx_review(
        docx_path=pack.docx_path,
        config_path=config,
        run="source",
        variant_id=None,
        project_dir=None,
    )
    assert result.run_id == "source"


def test_review_catalog_exposes_source_health(tmp_path: Path) -> None:
    config, run, pack = _review_workspace(tmp_path)

    def source():
        return list_review_summaries(config)[0]["source"]

    assert source()["state"] == "ready"
    assert source()["run_id"] == "source"
    _write_edited_docx(pack.docx_path)
    assert source()["state"] == "ready"
    (run / "canonical.md").write_text("Changed.\n")
    assert source()["state"] == "changed"
    (run / "canonical.md").unlink()
    assert source()["state"] == "missing"
    pack.source_record_path.write_text("{")
    assert source()["state"] == "invalid"
    pack.source_record_path.unlink()
    assert source()["state"] == "untracked"


def test_cli_imports_recorded_review_without_reselecting_a_run(tmp_path: Path) -> None:
    config, run, pack = _review_workspace(tmp_path)
    _write_edited_docx(pack.docx_path)
    result = CliRunner().invoke(
        app,
        [
            "import-docx",
            "--from",
            str(pack.docx_path),
            "--config",
            str(config),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["run_id"] == "source"
    (run / "canonical.md").write_text("Changed.\n")
    status = CliRunner().invoke(app, ["context", "--plain", "--config", str(config)])
    assert status.exit_code == 0, status.output
    assert "source=changed" in status.stdout


@pytest.mark.parametrize(
    "mutation", ["boolean_version", "missing_docx", "parent_path", "relative_run"]
)
def test_review_source_rejects_malformed_identity(tmp_path: Path, mutation: str) -> None:
    _, _, pack = _review_workspace(tmp_path)
    data = json.loads(pack.source_record_path.read_text())
    if mutation == "boolean_version":
        data["schema_version"] = True
    elif mutation == "missing_docx":
        del data["files"]["cv.docx"]
    elif mutation == "parent_path":
        data["files"]["../outside"] = "a" * 64
    else:
        data["run_path"] = "relative"
    pack.source_record_path.write_text(json.dumps(data))

    with pytest.raises(ReviewError, match="Invalid review source record"):
        load_source_record(pack.source_record_path)


def test_relative_project_run_path_preserves_source_identity(tmp_path: Path, monkeypatch) -> None:
    config = _write_minimal_config(tmp_path)
    _write_project_manifest(tmp_path, "job")
    run = tmp_path / "var" / "runs" / "projects" / "job" / "source"
    _write_run_manifest_at(run, variant_id="base", canonical="Original.\n", review_ready=True)
    monkeypatch.chdir(tmp_path)

    pack = build_review_pack(
        config_path=config, variant_id=None, run="var/runs/projects/job/source"
    )

    assert pack.run_id == "projects/job/source"
    assert pack.out_dir == tmp_path / "var" / "reviews" / "projects" / "job"


def test_review_catalog_uses_recorded_output_names(tmp_path: Path) -> None:
    config, run, _ = _review_workspace(tmp_path)
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for fmt in ("docx", "pdf"):
        (run / f"cv.{fmt}").rename(run / f"letter.{fmt}")
        manifest["outputs"][fmt] = f"letter.{fmt}"
    manifest_path.write_text(json.dumps(manifest))
    pack = build_review_pack(config_path=config, variant_id=None, run="source", force=True)

    entry = list_review_summaries(config)[0]
    assert entry["docx"] == str(pack.docx_path)
    assert entry["pdf"] == str(pack.pdf_path)
    assert entry["missing_files"] == []


@pytest.mark.parametrize("selection", ["{", "[]", '{"items": false}'])
def test_invalid_selection_preserves_existing_review_on_force(
    tmp_path: Path, selection: str
) -> None:
    config, run, pack = _review_workspace(tmp_path)
    _write_edited_docx(pack.docx_path)
    before = {p.name: p.read_bytes() for p in pack.out_dir.iterdir()}
    (run / "selection.json").write_text(selection)

    with pytest.raises(ReviewError, match="Selection metadata"):
        build_review_pack(config_path=config, variant_id=None, run="source", force=True)
    assert {p.name: p.read_bytes() for p in pack.out_dir.iterdir()} == before


def test_failed_replacement_preserves_edited_review_bundle(tmp_path: Path, monkeypatch) -> None:
    config, _, pack = _review_workspace(tmp_path)
    _write_edited_docx(pack.docx_path)
    before = {p.name: p.read_bytes() for p in pack.out_dir.iterdir()}
    original_replace = atomic.os.replace

    def fail_record_write(source, target):
        if Path(target) == pack.source_record_path:
            raise OSError("Injected record write failure")
        return original_replace(source, target)

    monkeypatch.setattr(atomic.os, "replace", fail_record_write)
    with pytest.raises(RuntimeError):
        build_review_pack(config_path=config, variant_id=None, run="source", force=True)
    assert {p.name: p.read_bytes() for p in pack.out_dir.iterdir()} == before


@pytest.mark.parametrize("target_kind", ["review_store", "source_run"])
def test_review_target_cannot_replace_store_or_source(tmp_path: Path, target_kind: str) -> None:
    config, run, pack = _review_workspace(tmp_path)
    target = pack.out_dir.parent if target_kind == "review_store" else run

    with pytest.raises(ReviewError, match="Review target"):
        build_review_pack(
            config_path=config, variant_id=None, run="source", out_dir=target, force=True
        )
    assert (run / "canonical.md").read_text() == "Original baseline.\n"
    assert pack.source_record_path.is_file()


def test_recorded_import_keeps_project_variant_selectors_exclusive(tmp_path: Path) -> None:
    config, _, pack = _review_workspace(tmp_path)
    with pytest.raises(ReviewError, match="--project cannot be combined with --variant"):
        import_docx_review(
            docx_path=pack.docx_path,
            config_path=config,
            run=None,
            variant_id="base",
            project_dir=tmp_path / "unused-project",
        )
    assert not (tmp_path / "var" / "drafts").exists()
