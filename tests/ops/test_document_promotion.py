"""Promote exact reviewed career files while preserving their predecessor."""

import json
from pathlib import Path

import pytest


def manual_request(root: Path, content: bytes = b"first draft") -> Path:
    working = root / "working" / "Unusual application name"
    working.mkdir(parents=True, exist_ok=True)
    (working / "CV edited.docx").write_bytes(content)
    request = working / "promotion.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document": {
                    "id": "general-cv",
                    "kind": "cv",
                    "edition": "general",
                    "audience": "application",
                },
                "source": {"kind": "authored", "path": "CV edited.docx"},
                "files": [
                    {"source": "CV edited.docx", "destination": "current/cv/application/cv.docx"}
                ],
            }
        )
    )
    return request


def test_manual_promotion_preserves_previous_and_records_source(tmp_path: Path) -> None:
    from cvworkbench.ops.documents.promotion import apply_promotion, plan_promotion
    from cvworkbench.workspace.documents import inspect_documents

    request = manual_request(tmp_path)
    plan = plan_promotion(request_path=request, root=tmp_path)
    destination = tmp_path / "current/cv/application/cv.docx"
    assert not destination.exists()
    receipt = apply_promotion(plan, reviewed_sha256=plan.sha256)
    assert destination.read_bytes() == b"first draft"
    assert receipt.is_file()
    request = manual_request(tmp_path, b"revised draft")
    plan = plan_promotion(request_path=request, root=tmp_path)
    receipt = apply_promotion(plan, reviewed_sha256=plan.sha256)
    assert destination.read_bytes() == b"revised draft"
    record = json.loads(receipt.read_text())
    assert (tmp_path / record["previous_files"][0]["archive"]).read_bytes() == b"first draft"
    item = next(
        item
        for item in inspect_documents(root=tmp_path)["items"]
        if item["path"] == str(destination)
    )
    assert item["state"] == "current"
    assert item["document"]["id"] == "general-cv"
    assert item["source"]["path"] == str(request.parent / "CV edited.docx")


@pytest.mark.parametrize("changed", ["source", "request", "destination"])
def test_changed_inputs_after_review_cannot_promote(tmp_path: Path, changed: str) -> None:
    from cvworkbench.ops.documents.promotion import apply_promotion, plan_promotion

    request = manual_request(tmp_path)
    plan = plan_promotion(request_path=request, root=tmp_path)
    target = tmp_path / "current/cv/application/cv.docx"
    if changed == "source":
        (request.parent / "CV edited.docx").write_bytes(b"unreviewed")
    elif changed == "request":
        request.write_text(request.read_text() + " ")
    else:
        target.parent.mkdir(parents=True)
        target.write_bytes(b"manual edit")
    with pytest.raises(ValueError):
        apply_promotion(plan, reviewed_sha256=plan.sha256)
    assert not (tmp_path / "records/promotions").exists()
    if changed == "destination":
        assert target.read_bytes() == b"manual edit"


def test_manual_edit_is_visible_and_cannot_be_overwritten(tmp_path: Path) -> None:
    from cvworkbench.ops.documents.promotion import apply_promotion, plan_promotion
    from cvworkbench.workspace.documents import inspect_documents

    request = manual_request(tmp_path)
    plan = plan_promotion(request_path=request, root=tmp_path)
    apply_promotion(plan, reviewed_sha256=plan.sha256)
    target = tmp_path / "current/cv/application/cv.docx"
    target.write_bytes(b"edited in Word")
    current = next(
        i for i in inspect_documents(root=tmp_path)["items"] if i["location"] == "current"
    )
    assert current["state"] == "modified"
    with pytest.raises(ValueError, match="manual edits"):
        plan_promotion(request_path=request, root=tmp_path)


def test_receipt_metadata_tampering_cannot_change_identity(tmp_path: Path) -> None:
    from cvworkbench.ops.documents.promotion import apply_promotion, plan_promotion
    from cvworkbench.workspace.documents import inspect_documents

    request = manual_request(tmp_path)
    plan = plan_promotion(request_path=request, root=tmp_path)
    receipt = apply_promotion(plan, reviewed_sha256=plan.sha256)
    record = json.loads(receipt.read_text())
    record["source"] = {"kind": "authored", "path": "/unrelated/file.docx"}
    receipt.write_text(json.dumps(record))
    result = inspect_documents(root=tmp_path)
    assert result["issues"]
    with pytest.raises(ValueError):
        plan_promotion(request_path=request, root=tmp_path)


def test_mismatched_file_extension_rejected(tmp_path: Path) -> None:
    from cvworkbench.ops.documents.promotion import plan_promotion

    request = manual_request(tmp_path)
    data = json.loads(request.read_text())
    data["files"][0]["destination"] = "current/cv/cv.pdf"
    request.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="extension"):
        plan_promotion(request_path=request, root=tmp_path)


def test_native_source_requires_current_build_and_protects_run(tmp_path: Path) -> None:
    from cvworkbench.ops.documents.promotion import apply_promotion, plan_promotion
    from tests.ops.publication.test_native import native_workspace

    args = native_workspace(tmp_path)
    request = tmp_path / "promotion.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document": {
                    "id": "native-cv",
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
                    {
                        "source": str(args["run_path"] / "cv.pdf"),
                        "destination": "current/native/cv.pdf",
                    }
                ],
            }
        )
    )
    plan = plan_promotion(request_path=request, root=tmp_path)
    receipt = apply_promotion(plan, reviewed_sha256=plan.sha256)
    assert json.loads(receipt.read_text())["plan"]["source"]["run_path"] == str(args["run_path"])
    (args["sot_path"] / "education.yaml").write_text("changed: true\n")
    with pytest.raises(ValueError, match="source|inputs"):
        plan_promotion(request_path=request, root=tmp_path)


def test_public_promotion_requires_reviewed_exact_publication(tmp_path: Path) -> None:
    from cvworkbench.ops.documents.promotion import apply_promotion, plan_promotion
    from cvworkbench.ops.publication.native import prepare_native_public_pdf
    from cvworkbench.ops.publication.record import hash_file
    from cvworkbench.ops.publication.state import record_publication_review
    from tests.ops.publication.test_native import native_workspace

    args = native_workspace(tmp_path)
    prepared = prepare_native_public_pdf(**args)
    request = tmp_path / "promotion.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document": {
                    "id": "public-cv",
                    "kind": "cv",
                    "edition": "general",
                    "audience": "public",
                },
                "source": {
                    "kind": "publication",
                    "config": str(args["config_path"]),
                    "variant": "base",
                },
                "files": [
                    {"source": str(prepared.output_pdf), "destination": "current/cv/public/cv.pdf"}
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="review"):
        plan_promotion(request_path=request, root=tmp_path)
    record_publication_review(args["config_path"], "base", hash_file(prepared.output_pdf))
    plan = plan_promotion(request_path=request, root=tmp_path)
    apply_promotion(plan, reviewed_sha256=plan.sha256)
    assert (tmp_path / "current/cv/public/cv.pdf").read_bytes() == prepared.output_pdf.read_bytes()
    data = json.loads(request.read_text())
    data["files"][0]["source"] = str(args["run_path"] / "cv.pdf")
    request.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="exact"):
        plan_promotion(request_path=request, root=tmp_path)


def test_failed_replacement_recovers_current_files_and_history(tmp_path, monkeypatch):
    from cvworkbench import storage
    from cvworkbench.ops.documents.promotion import apply_promotion, plan_promotion

    request = manual_request(tmp_path)
    plan = plan_promotion(request_path=request, root=tmp_path)
    apply_promotion(plan, reviewed_sha256=plan.sha256)
    before = {
        p: p.read_bytes()
        for folder in ("current", "records", "archive")
        for p in (tmp_path / folder).rglob("*")
        if p.is_file()
    }
    manual_request(tmp_path, b"new draft")
    plan = plan_promotion(request_path=request, root=tmp_path)
    original = storage.os.replace
    target = tmp_path / "current/cv/application/cv.docx"
    failed = False

    def fail_after_replace(source, destination):
        nonlocal failed
        original(source, destination)
        if Path(destination) == target and not failed:
            failed = True
            raise OSError("injected replacement failure")

    monkeypatch.setattr(storage.os, "replace", fail_after_replace)
    with pytest.raises(storage.AtomicWriteError):
        apply_promotion(plan, reviewed_sha256=plan.sha256)
    after = {
        p: p.read_bytes()
        for folder in ("current", "records", "archive")
        for p in (tmp_path / folder).rglob("*")
        if p.is_file()
    }
    assert after == before


@pytest.mark.parametrize(
    "destination", ["../escaped.docx", "current/../escaped.docx", "/absolute.docx"]
)
def test_promotion_rejects_escaped_paths_before_any_write(tmp_path, destination):
    from cvworkbench.ops.documents.promotion import plan_promotion

    request = manual_request(tmp_path)
    data = json.loads(request.read_text())
    data["files"][0]["destination"] = destination
    request.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        plan_promotion(request_path=request, root=tmp_path)
    assert not (tmp_path / "current").exists()


def test_promotion_rejects_linked_destination_directory(tmp_path):
    from cvworkbench.ops.documents.promotion import plan_promotion

    request = manual_request(tmp_path)
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "current").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        plan_promotion(request_path=request, root=tmp_path)
    assert list((tmp_path / "elsewhere").iterdir()) == []


def test_file_set_can_evolve_without_losing_removed_artifacts(tmp_path):
    from cvworkbench.ops.documents.promotion import apply_promotion, plan_promotion

    request = manual_request(tmp_path)
    plan = plan_promotion(request_path=request, root=tmp_path)
    apply_promotion(plan, reviewed_sha256=plan.sha256)
    data = json.loads(request.read_text())
    data["files"][0]["destination"] = "current/cv/application/better-name.docx"
    request.write_text(json.dumps(data))
    plan = plan_promotion(request_path=request, root=tmp_path)
    assert plan.payload["retired_files"][0]["destination"] == "current/cv/application/cv.docx"
    receipt = apply_promotion(plan, reviewed_sha256=plan.sha256)
    assert not (tmp_path / "current/cv/application/cv.docx").exists()
    assert (tmp_path / "current/cv/application/better-name.docx").read_bytes() == b"first draft"
    record = json.loads(receipt.read_text())
    assert (tmp_path / record["previous_files"][0]["archive"]).read_bytes() == b"first draft"


def test_explicit_manual_edit_reconciliation_archives_changed_current(tmp_path):
    from cvworkbench.ops.documents.promotion import apply_promotion, plan_promotion

    request = manual_request(tmp_path)
    plan = plan_promotion(request_path=request, root=tmp_path)
    apply_promotion(plan, reviewed_sha256=plan.sha256)
    target = tmp_path / "current/cv/application/cv.docx"
    target.write_bytes(b"manual edit to preserve")
    data = json.loads(request.read_text())
    data["replace_modified_current"] = True
    request.write_text(json.dumps(data))
    plan = plan_promotion(request_path=request, root=tmp_path)
    receipt = apply_promotion(plan, reviewed_sha256=plan.sha256)
    record = json.loads(receipt.read_text())
    assert (
        tmp_path / record["previous_files"][0]["archive"]
    ).read_bytes() == b"manual edit to preserve"


def test_concurrent_promotions_cannot_overwrite_each_other(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from cvworkbench.ops.documents import promotion

    request = manual_request(tmp_path)
    first = promotion.plan_promotion(request_path=request, root=tmp_path)
    second_request = request.with_name("second.json")
    data = json.loads(request.read_text())
    data["document"]["id"] = "another-document"
    second_request.write_text(json.dumps(data))
    second = promotion.plan_promotion(request_path=second_request, root=tmp_path)
    entered, release = Event(), Event()
    original = promotion.replace_files_atomically

    def paused_commit(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(promotion, "replace_files_atomically", paused_commit)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            promotion.apply_promotion, first, reviewed_sha256=first.sha256
        )
        assert entered.wait(5)
        try:
            with pytest.raises(ValueError, match="progress|busy"):
                promotion.apply_promotion(second, reviewed_sha256=second.sha256)
        finally:
            release.set()
        assert first_future.result().is_file()


def test_manual_reconciliation_does_not_authorize_unrecorded_new_destination(tmp_path):
    from cvworkbench.ops.documents.promotion import apply_promotion, plan_promotion

    request = manual_request(tmp_path)
    plan = plan_promotion(request_path=request, root=tmp_path)
    apply_promotion(plan, reviewed_sha256=plan.sha256)
    unrelated = tmp_path / "current/unrelated.docx"
    unrelated.write_bytes(b"independent document")
    data = json.loads(request.read_text())
    data["replace_modified_current"] = True
    data["files"][0]["destination"] = "current/unrelated.docx"
    request.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Unrecorded"):
        plan_promotion(request_path=request, root=tmp_path)
    assert unrelated.read_bytes() == b"independent document"


def test_destination_aliases_are_rejected_during_preview(tmp_path):
    from cvworkbench.ops.documents.promotion import plan_promotion

    request = manual_request(tmp_path)
    data = json.loads(request.read_text())
    data["files"].append({**data["files"][0], "destination": "current/cv//application/cv.docx"})
    request.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="unique|canonical"):
        plan_promotion(request_path=request, root=tmp_path)


def test_promotion_cannot_retire_an_additional_artifact_source(tmp_path):
    from cvworkbench.ops.documents.promotion import apply_promotion, plan_promotion

    request = manual_request(tmp_path)
    plan = plan_promotion(request_path=request, root=tmp_path)
    apply_promotion(plan, reviewed_sha256=plan.sha256)
    data = json.loads(request.read_text())
    data["files"] = [
        {
            "source": str(tmp_path / "current/cv/application/cv.docx"),
            "destination": "current/another.docx",
        }
    ]
    request.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="source"):
        plan_promotion(request_path=request, root=tmp_path)


def test_missing_current_remains_discoverable(tmp_path):
    from cvworkbench.ops.documents.promotion import apply_promotion, plan_promotion
    from cvworkbench.workspace.documents import inspect_documents

    request = manual_request(tmp_path)
    plan = plan_promotion(request_path=request, root=tmp_path)
    apply_promotion(plan, reviewed_sha256=plan.sha256)
    destination = tmp_path / "current/cv/application/cv.docx"
    destination.unlink()
    result = inspect_documents(root=tmp_path)
    current = [item for item in result["items"] if item["location"] == "current"]
    assert len(current) == 1
    assert current[0]["state"] == "missing"
    assert current[0]["source"]["path"] == str(request.parent / "CV edited.docx")
    assert result["issues"]
    selected = inspect_documents(root=tmp_path, paths=[request.parent])
    assert not [item for item in selected["items"] if item["location"] == "current"]
