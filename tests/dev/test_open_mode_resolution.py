"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/dev/test_open_mode_resolution.py

Tests open mode resolution rules.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import pytest

from cvworkbench.dev.open import OpenMode, resolve_open_mode


def test_resolve_open_mode_env_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CVW_SKIP_OPEN", "1")

    assert resolve_open_mode(None) is OpenMode.NONE


def test_resolve_open_mode_prefers_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CVW_SKIP_OPEN", raising=False)

    assert resolve_open_mode(OpenMode.APPLESCRIPT) is OpenMode.APPLESCRIPT
