"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/utils.py

Test helpers for CLI output normalization.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return _ANSI_PATTERN.sub("", text)


@contextmanager
def isolated_filesystem(*, temp_dir: Path) -> Iterator[str]:
    """Provide a temporary working directory independently of a CLI runner."""

    original_directory = Path.cwd()
    working_directory = Path(tempfile.mkdtemp(dir=temp_dir))
    os.chdir(working_directory)
    try:
        yield str(working_directory)
    finally:
        os.chdir(original_directory)
