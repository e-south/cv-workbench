"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/dev/test_open.py

Tests browser open helpers for preview.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from typing import Any

import pytest

from cvworkbench.dev.open import OpenMode, open_url


class _RunRecorder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.returncode = 0
        self.stderr = ""
        self.stdout = ""

    def __call__(self, args: list[str], **kwargs: Any) -> Any:
        self.calls.append(args)
        if self.returncode != 0:
            message = (self.stderr or self.stdout or "").strip()
            return False, message or "Browser open failed"
        return True, None


def test_open_url_launchservices_default(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _RunRecorder()
    monkeypatch.setattr("cvworkbench.dev.open._run_command", runner)
    monkeypatch.setattr("cvworkbench.dev.open.sys.platform", "darwin")

    result = open_url("http://localhost:8000", mode=OpenMode.LAUNCHSERVICES, browser=None)

    assert result.opened is True
    assert result.error is None
    assert runner.calls == [["/usr/bin/open", "http://localhost:8000"]]


def test_open_url_launchservices_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _RunRecorder()
    monkeypatch.setattr("cvworkbench.dev.open._run_command", runner)
    monkeypatch.setattr("cvworkbench.dev.open.sys.platform", "darwin")

    result = open_url(
        "http://localhost:8000",
        mode=OpenMode.LAUNCHSERVICES,
        browser="Google Chrome",
    )

    assert result.opened is True
    assert result.error is None
    assert runner.calls == [
        ["/usr/bin/open", "-a", "Google Chrome", "http://localhost:8000"]
    ]


def test_open_url_none_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _RunRecorder()
    monkeypatch.setattr("cvworkbench.dev.open._run_command", runner)

    result = open_url("http://localhost:8000", mode=OpenMode.NONE, browser=None)

    assert result.opened is False
    assert result.error is None
    assert runner.calls == []


def test_open_url_applescript_error(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _RunRecorder()
    runner.returncode = 1
    runner.stderr = "not authorized"
    monkeypatch.setattr("cvworkbench.dev.open._run_command", runner)
    monkeypatch.setattr("cvworkbench.dev.open.sys.platform", "darwin")

    result = open_url(
        "http://localhost:8000",
        mode=OpenMode.APPLESCRIPT,
        browser="Google Chrome",
    )

    assert result.opened is False
    assert result.error == "not authorized"
