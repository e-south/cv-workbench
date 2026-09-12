"""Career document discovery includes ordinary files without a native source."""

from pathlib import Path

import pytest


def test_discover_manual_documents_without_config_or_metadata(tmp_path: Path) -> None:
    from cvworkbench.workspace.documents import inspect_documents

    root = tmp_path / "career"
    working = root / "working" / "A named application"
    working.mkdir(parents=True)
    manual = working / "My CV (edits).docx"
    manual.write_bytes(b"manual content")
    (working / "README.md").write_text("operator notes")
    (root / "archive").mkdir()
    (root / "archive" / "old.pdf").write_bytes(b"old")
    result = inspect_documents(root=root)
    assert result["issues"] == []
    assert len(result["items"]) == 1
    assert result["items"][0]["path"] == str(manual)
    assert result["items"][0]["state"] == "unrecorded"
    assert result["items"][0]["document"] is None
    assert result["items"][0]["location"] == "working"
    assert result["recipes"] == []


def test_configured_discovery_lists_recipes_and_excludes_generated_inputs(
    sample_workspace: Path,
) -> None:
    from cvworkbench.workspace.documents import inspect_documents

    config = sample_workspace / "config/workbench.yaml"
    config.write_text(config.read_text() + "\ndocuments:\n  root: ..\n")
    review = sample_workspace / "working/specific-purpose/review.pdf"
    review.parent.mkdir(parents=True)
    review.write_bytes(b"review")
    result = inspect_documents(config_path=config)
    assert str(review) in {item["path"] for item in result["items"]}
    assert "base" in {recipe["id"] for recipe in result["recipes"]}
    assert result["recipes"][0]["config"] == str(config)


def test_explicit_selection_does_not_scan_unrelated_documents(tmp_path: Path) -> None:
    from cvworkbench.workspace.documents import inspect_documents

    selected = tmp_path / "Anything.docx"
    selected.write_bytes(b"selected")
    result = inspect_documents(root=tmp_path, paths=[selected])
    assert [item["path"] for item in result["items"]] == [str(selected)]
    with pytest.raises(ValueError, match="outside"):
        inspect_documents(root=tmp_path, paths=[tmp_path.parent])
