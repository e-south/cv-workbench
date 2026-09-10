"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_atomic.py

Verifies artifact recovery under staging and rollback failures.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from pathlib import Path

import pytest

from cvworkbench.ops import atomic


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
