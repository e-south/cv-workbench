"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/utils.py

Test helpers for CLI output normalization.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import re

_ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return _ANSI_PATTERN.sub("", text)
