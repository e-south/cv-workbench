"""Promotion and native publication dependencies survive run cleanup."""

import json

import pytest

from cvworkbench.ops.runs import RunError, gc_runs
from tests.ops.publication.test_native import native_workspace


def add_run_catalog_metadata(args):
    manifest = args["run_path"] / "manifest.json"
    data = json.loads(manifest.read_text())
    data.update({"created_at": "2026-01-01T00:00:00+00:00", "formats": ["md", "pdf"]})
    manifest.write_text(json.dumps(data))


def test_native_publication_retains_source_run_even_without_content_review(tmp_path):
    from cvworkbench.ops.publication.native import prepare_native_public_pdf

    args = native_workspace(tmp_path)
    add_run_catalog_metadata(args)
    prepare_native_public_pdf(**args)
    summary = gc_runs(
        config_path=args["config_path"], keep_latest=0, keep=[], include_invalid=True, confirm=True
    )
    assert summary.removed == 0
    assert args["run_path"].exists()
    assert any(
        "publication:" in reason for reasons in summary.keep_reasons.values() for reason in reasons
    )


def test_promoted_native_run_retained_even_after_source_changes(tmp_path):
    from cvworkbench.ops.documents.promotion import apply_promotion, plan_promotion

    args = native_workspace(tmp_path)
    add_run_catalog_metadata(args)
    request = tmp_path / "promotion.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document": {
                    "id": "cv",
                    "kind": "cv",
                    "edition": "general",
                    "audience": "application",
                },
                "source": {
                    "kind": "native",
                    "config": str(args["config_path"]),
                    "path": str(args["sot_path"]),
                    "variant": "base",
                    "run": str(args["run_path"]),
                },
                "files": [
                    {"source": str(args["run_path"] / "cv.pdf"), "destination": "current/cv/cv.pdf"}
                ],
            }
        )
    )
    plan = plan_promotion(request_path=request, root=tmp_path)
    apply_promotion(plan, reviewed_sha256=plan.sha256)
    config = args["config_path"]
    config.write_text(config.read_text() + "\ndocuments:\n  root: ..\n")
    (args["sot_path"] / "person.yaml").write_text("changed: true\n")
    summary = gc_runs(
        config_path=config, keep_latest=0, keep=[], include_invalid=True, confirm=True
    )
    assert summary.removed == 0
    assert args["run_path"].exists()
    assert any(
        "promotion:" in reason for reasons in summary.keep_reasons.values() for reason in reasons
    )


def test_invalid_publication_record_blocks_cleanup(tmp_path):
    args = native_workspace(tmp_path)
    add_run_catalog_metadata(args)
    record = tmp_path / "var/publish/base/preparation.json"
    record.parent.mkdir(parents=True)
    record.write_text('{"kind":"native-build"}')
    with pytest.raises(RunError, match="publication"):
        gc_runs(
            config_path=args["config_path"],
            keep_latest=0,
            keep=[],
            include_invalid=True,
            confirm=True,
        )
    assert args["run_path"].exists()
