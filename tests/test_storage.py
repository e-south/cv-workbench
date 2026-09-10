"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/test_storage.py

Verifies artifact recovery under staging and rollback failures.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from pathlib import Path

import pytest

from cvworkbench import storage as atomic


def test_changed_expected_contents_fail_before_staging(tmp_path):
    existing = tmp_path / "existing.txt"
    existing.write_bytes(b"editor's change")
    new = tmp_path / "new/artifact.txt"

    with pytest.raises(atomic.AtomicWriteError, match="changed"):
        atomic.replace_files_atomically(
            [(new, b"new output"), (existing, b"replacement")],
            expected_contents={new: None, existing: b"original"},
        )

    assert existing.read_bytes() == b"editor's change"
    assert not new.parent.exists()


def test_expected_contents_are_rechecked_after_staging(tmp_path, monkeypatch):
    first, second = tmp_path / "first.txt", tmp_path / "second.txt"
    first.write_bytes(b"first original")
    second.write_bytes(b"second original")
    original_copy = atomic.shutil.copy2

    def edit_after_backup(source, target, *args, **kwargs):
        result = original_copy(source, target, *args, **kwargs)
        if source == second:
            first.write_bytes(b"editor's change")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(atomic.shutil, "copy2", edit_after_backup)
        with pytest.raises(atomic.AtomicWriteError, match="changed"):
            atomic.replace_files_atomically(
                [(first, b"replacement one"), (second, b"replacement two")],
                expected_contents={first: b"first original", second: b"second original"},
            )

    assert first.read_bytes() == b"editor's change"
    assert second.read_bytes() == b"second original"
    assert set(tmp_path.iterdir()) == {first, second}


def test_expected_absence_allows_creation_and_rejects_existing_empty_files(tmp_path):
    target = tmp_path / "new.txt"
    atomic.replace_files_atomically([(target, b"")], expected_contents={target: None})
    with pytest.raises(atomic.AtomicWriteError, match="changed"):
        atomic.replace_files_atomically([(target, b"overwrite")], expected_contents={target: None})
    assert target.read_bytes() == b""


def test_expected_absence_preserves_a_dangling_symlink(tmp_path):
    target = tmp_path / "existing-link"
    target.symlink_to(tmp_path / "missing")
    with pytest.raises(atomic.AtomicWriteError, match="changed"):
        atomic.replace_files_atomically([(target, b"new")], expected_contents={target: None})
    assert target.is_symlink()


@pytest.mark.parametrize("invalid", ["destination", "text", "boolean", "mapping"])
def test_invalid_expected_contents_fail_before_writes(tmp_path, invalid):
    target = tmp_path / "output/data.txt"
    expected = {
        "destination": {tmp_path / "other.txt": b"original"},
        "text": {target: "original"},
        "boolean": {target: False},
        "mapping": [],
    }[invalid]
    with pytest.raises(atomic.AtomicWriteError, match="Expected contents"):
        atomic.replace_files_atomically([(target, b"new")], expected_contents=expected)
    assert not target.parent.exists()


@pytest.mark.parametrize("mode", [True, -1, 0o4777])
def test_invalid_file_modes_fail_before_creating_outputs(tmp_path, mode):
    target = tmp_path / "output/data.json"
    with pytest.raises(atomic.AtomicWriteError, match="permission bits"):
        atomic.replace_files_atomically([(target, b"private")], file_modes={target: mode})
    assert not target.parent.exists()


def test_failed_rollback_retains_original_recovery_copy(tmp_path, monkeypatch):
    first, second = tmp_path / "first.pdf", tmp_path / "manifest.json"
    first.write_bytes(b"original PDF")
    second.write_bytes(b"original manifest")
    replace = atomic.os.replace

    def fail_replace(source, destination):
        if Path(destination) == second or "cvw-backup" in Path(source).name:
            raise OSError("injected replacement failure")
        return replace(source, destination)

    monkeypatch.setattr(atomic.os, "replace", fail_replace)
    with pytest.raises(atomic.AtomicWriteError, match="rollback was incomplete"):
        atomic.replace_files_atomically([(first, b"updated PDF"), (second, b"updated manifest")])

    backups = list(tmp_path.glob(".first.pdf.cvw-backup-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"original PDF"
    assert second.read_bytes() == b"original manifest"
    assert not list(tmp_path.glob("*.cvw-stage-*"))


def test_failed_backup_staging_leaves_no_temporary_files(tmp_path, monkeypatch):
    destination = tmp_path / "cv.pdf"
    destination.write_bytes(b"original")

    def fail_copy(source, target):
        raise OSError("injected backup failure")

    monkeypatch.setattr(atomic.shutil, "copy2", fail_copy)
    with pytest.raises(atomic.AtomicWriteError):
        atomic.replace_files_atomically([(destination, b"updated")])

    assert destination.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("timing", ["before", "after"])
@pytest.mark.parametrize("existing", [True, False])
def test_interruption_restores_replaced_files(tmp_path, monkeypatch, timing, existing):
    first, second = tmp_path / "first.txt", tmp_path / "second.txt"
    if existing:
        first.write_bytes(b"first original")
        second.write_bytes(b"second original")
    original = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    replace = atomic.os.replace

    def interrupt(source, destination):
        is_target = Path(destination) == second and "cvw-stage" in Path(source).name
        if is_target and timing == "before":
            raise KeyboardInterrupt("cancel commit")
        result = replace(source, destination)
        if is_target:
            raise KeyboardInterrupt("cancel commit")
        return result

    monkeypatch.setattr(atomic.os, "replace", interrupt)
    with pytest.raises(KeyboardInterrupt, match="cancel commit"):
        atomic.replace_files_atomically([(first, b"new first"), (second, b"new second")])
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == original


def test_alias_destinations_are_rejected_before_writes(tmp_path):
    directory = tmp_path / "actual"
    directory.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(directory, target_is_directory=True)
    with pytest.raises(atomic.AtomicWriteError, match="unique"):
        atomic.replace_files_atomically(
            [(directory / "new.txt", b"one"), (alias / "new.txt", b"two")]
        )
    assert not list(directory.iterdir())


@pytest.mark.parametrize("error", [OSError, KeyboardInterrupt])
def test_failed_commit_releases_its_empty_parent_directories(tmp_path, monkeypatch, error):
    existing = tmp_path / "existing.txt"
    existing.write_bytes(b"original")
    target = tmp_path / "new/nested/output.txt"
    replace = atomic.os.replace

    def fail(source, destination):
        if Path(destination) == existing and "cvw-stage" in Path(source).name:
            raise error("cancel")
        return replace(source, destination)

    monkeypatch.setattr(atomic.os, "replace", fail)
    with pytest.raises(atomic.AtomicWriteError if error is OSError else error):
        atomic.replace_files_atomically([(target, b"new"), (existing, b"updated")])
    assert existing.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [existing]


@pytest.mark.parametrize("kind", ["symlink", "directory"])
def test_nonregular_destination_fails_before_creating_other_parents(tmp_path, kind):
    source = tmp_path / "source.txt"
    source.write_bytes(b"original")
    target = tmp_path / "target"
    if kind == "symlink":
        target.symlink_to(source)
    else:
        target.mkdir()
    new = tmp_path / "new/output.txt"
    with pytest.raises(atomic.AtomicWriteError, match="regular files"):
        atomic.replace_files_atomically([(new, b"new"), (target, b"replacement")])
    assert source.read_bytes() == b"original"
    assert target.is_symlink() if kind == "symlink" else target.is_dir()
    assert not new.parent.exists()
