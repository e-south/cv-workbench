"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_runs.py

Verify run allocation cleans only its own empty directories after failure.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from pathlib import Path

import pytest

from cvworkbench.build.runs import allocate_run


@pytest.mark.parametrize("error", [OSError, KeyboardInterrupt])
def test_run_failure_cleans_created_parents_and_preserves_original_error(tmp_path, error):
    existing = tmp_path / "runs"
    existing.mkdir()
    note = existing / "operator-note.txt"
    note.write_text("Keep this note.\n")
    failure = error("commit failed")
    with pytest.raises(error) as caught:
        with allocate_run(existing / "projects/research"):
            raise failure
    assert caught.value is failure
    assert list(existing.iterdir()) == [note]
    assert note.read_text() == "Keep this note.\n"


def test_allocation_failure_cleans_parents_without_a_run(tmp_path, monkeypatch):
    root = tmp_path / "runs/projects/research"
    mkdir = Path.mkdir

    def refuse_run(path, *args, **kwargs):
        if path.parent == root:
            raise PermissionError("run directory denied")
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", refuse_run)
    with pytest.raises(PermissionError, match="run directory denied"):
        with allocate_run(root):
            pytest.fail("allocation must not yield")
    assert not list(tmp_path.iterdir())


def test_replaced_empty_run_is_preserved(tmp_path):
    root = tmp_path / "runs"
    saved = tmp_path / "original-run"
    with pytest.raises(OSError) as caught:
        with allocate_run(root) as run:
            run.rename(saved)
            run.mkdir()
            replacement_inode = run.stat().st_ino
            raise OSError("commit failed")
    assert run.is_dir()
    assert run.stat().st_ino == replacement_inode
    assert saved.is_dir()
    assert caught.value.__notes__ == [f"Build directory retained for inspection: {run}"]


def test_nonempty_run_is_preserved_with_one_actionable_diagnostic(tmp_path):
    with pytest.raises(OSError) as caught:
        with allocate_run(tmp_path / "runs/projects/research") as run:
            note = run / "recovery.txt"
            note.write_text("Keep recovery evidence.\n")
            raise OSError("commit failed")
    assert note.read_text() == "Keep recovery evidence.\n"
    assert caught.value.__notes__ == [f"Build directory retained for inspection: {run}"]
