"""Serialize cooperating promotions without waiting on another editing session."""

import os
from contextlib import contextmanager
from pathlib import Path

from cvworkbench.ops.documents.records import DocumentError, regular_path


@contextmanager
def promotion_lock(root: Path):
    path = regular_path(root / "records/promotions/.lock", missing=True)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "r+b") as handle:
        try:
            import fcntl
        except ImportError:
            import msvcrt

            if path.stat().st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise DocumentError(
                    "Another promotion is in progress; retry after it finishes"
                ) from exc
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise DocumentError(
                    "Another promotion is in progress; retry after it finishes"
                ) from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
