"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/dev/test_open.py

Tests browser open helpers for preview.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cvworkbench.dev.open import (
    OpenMode,
    PreviewViewer,
    open_pdf,
    open_pdf_in_preview,
    open_url,
    resolve_preview_viewer,
)


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


class _RunSequence:
    def __init__(self, results: list[tuple[bool, str | None]]) -> None:
        self.calls: list[list[str]] = []
        self._results = results

    def __call__(self, args: list[str], **kwargs: Any) -> Any:
        self.calls.append(args)
        if not self._results:
            return False, "No results queued"
        return self._results.pop(0)


class _SpawnRecorder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.returncode = 0
        self.error: str | None = None

    def __call__(self, args: list[str]) -> Any:
        self.calls.append(args)
        if self.returncode != 0:
            return False, self.error or "spawn failed"
        return True, None


def test_open_url_launchservices_default(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _RunRecorder()
    monkeypatch.setattr("cvworkbench.dev.open._run_command", runner)
    monkeypatch.setattr("cvworkbench.dev.open.sys.platform", "darwin")
    monkeypatch.setattr(
        "cvworkbench.dev.open._macos_browser_candidates",
        lambda: [("TestBrowser", Path("/Applications/TestBrowser.app"))],
    )
    monkeypatch.setattr("cvworkbench.dev.open._macos_default_handler_for_scheme", lambda _: None)

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
    assert runner.calls == [["/usr/bin/open", "-a", "Google Chrome", "http://localhost:8000"]]


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
    assert result.error is not None
    assert "Automation" in result.error


def test_open_url_launchservices_missing_handler_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _RunRecorder()
    runner.returncode = 1
    runner.stderr = "No application knows how to open URL file:///tmp/cv.html"
    monkeypatch.setattr("cvworkbench.dev.open._run_command", runner)
    monkeypatch.setattr("cvworkbench.dev.open.sys.platform", "darwin")

    result = open_url("file:///tmp/cv.html", mode=OpenMode.LAUNCHSERVICES, browser=None)

    assert result.opened is False
    assert result.error is not None
    assert "--browser" in result.error


def test_open_url_launchservices_fallback_to_safari(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _RunSequence(
        [
            (False, "No application knows how to open URL file:///tmp/cv.html"),
            (True, None),
        ]
    )
    monkeypatch.setattr("cvworkbench.dev.open._run_command", runner)
    monkeypatch.setattr("cvworkbench.dev.open.sys.platform", "darwin")
    monkeypatch.setattr(
        "cvworkbench.dev.open._macos_browser_candidates",
        lambda: [("TestBrowser", Path("/Applications/TestBrowser.app"))],
    )

    result = open_url("file:///tmp/cv.html", mode=OpenMode.LAUNCHSERVICES, browser=None)

    assert result.opened is True
    assert result.error is None
    assert result.note is not None
    assert "detected browser" in result.note
    assert runner.calls[0][0:2] == ["/usr/bin/open", "file:///tmp/cv.html"]
    assert runner.calls[1][0:3] == ["/usr/bin/open", "-a", "TestBrowser"]
    assert runner.calls[1][-1] == "file:///tmp/cv.html"


def test_open_url_launchservices_fallback_on_executable_format(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _RunSequence(
        [
            (
                False,
                "kLSExecutableIncorrectFormat: No compatible executable was found",
            ),
            (True, None),
        ]
    )
    monkeypatch.setattr("cvworkbench.dev.open._run_command", runner)
    monkeypatch.setattr("cvworkbench.dev.open.sys.platform", "darwin")
    monkeypatch.setattr(
        "cvworkbench.dev.open._macos_browser_candidates",
        lambda: [("TestBrowser", Path("/Applications/TestBrowser.app"))],
    )

    result = open_url("file:///tmp/cv.html", mode=OpenMode.LAUNCHSERVICES, browser=None)

    assert result.opened is True
    assert result.note is not None
    assert runner.calls[0][0:2] == ["/usr/bin/open", "file:///tmp/cv.html"]
    assert runner.calls[1][0:3] == ["/usr/bin/open", "-a", "TestBrowser"]


def test_open_pdf_uses_quicklook(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _SpawnRecorder()
    monkeypatch.setattr("cvworkbench.dev.open._spawn_quicklook", runner)
    monkeypatch.setattr(
        "cvworkbench.dev.open._run_command", lambda *_args, **_kwargs: (False, "no")
    )
    monkeypatch.setattr("cvworkbench.dev.open.sys.platform", "darwin")

    result = open_pdf(Path("/tmp/cv.pdf"))

    assert result.opened is True
    assert result.note is not None
    assert "Quick Look" in result.note
    assert runner.calls == [Path("/tmp/cv.pdf")]


def test_open_pdf_fallback_when_quicklook_crashes(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _SpawnRecorder()
    runner.returncode = 1
    runner.error = "Quick Look crashed"
    run_open = _RunRecorder()
    monkeypatch.setattr("cvworkbench.dev.open._spawn_quicklook", runner)
    monkeypatch.setattr("cvworkbench.dev.open._run_command", run_open)
    monkeypatch.setattr("cvworkbench.dev.open.sys.platform", "darwin")

    result = open_pdf(Path("/tmp/cv.pdf"))

    assert result.opened is True
    assert run_open.calls[0] == ["/usr/bin/open", "/tmp/cv.pdf"]


def test_open_pdf_fallback_to_direct_exec(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _SpawnRecorder()
    runner.returncode = 1
    runner.error = "Quick Look crashed"
    open_sequence = _RunSequence(
        [
            (False, "No application knows how to open URL file:///tmp/cv.pdf"),
            (False, "kLSNoExecutableErr"),
        ]
    )
    exec_spawn = _SpawnRecorder()
    monkeypatch.setattr("cvworkbench.dev.open._spawn_quicklook", runner)
    monkeypatch.setattr("cvworkbench.dev.open._run_command", open_sequence)
    monkeypatch.setattr("cvworkbench.dev.open._spawn_command", exec_spawn)
    monkeypatch.setattr("cvworkbench.dev.open.sys.platform", "darwin")
    monkeypatch.setattr(
        "cvworkbench.dev.open._macos_pdf_viewer_candidates",
        lambda: [("Preview", Path("/Applications/Preview.app"))],
    )
    monkeypatch.setattr(
        "cvworkbench.dev.open._app_executable_path",
        lambda path: path / "Contents" / "MacOS" / "Preview",
    )

    result = open_pdf(Path("/tmp/cv.pdf"))

    assert result.opened is True
    assert exec_spawn.calls[0] == [
        "/Applications/Preview.app/Contents/MacOS/Preview",
        "/tmp/cv.pdf",
    ]


def test_open_pdf_in_preview_uses_preview_app(monkeypatch: pytest.MonkeyPatch) -> None:
    run_open = _RunRecorder()
    monkeypatch.setattr("cvworkbench.dev.open._run_command", run_open)
    monkeypatch.setattr("cvworkbench.dev.open.sys.platform", "darwin")
    monkeypatch.setattr("cvworkbench.dev.open._preview_process_running", lambda: True)

    result = open_pdf_in_preview(Path("/tmp/cv.pdf"))

    assert result.opened is True
    assert run_open.calls[0] == ["/usr/bin/open", "-a", "Preview", "/tmp/cv.pdf"]


def test_open_pdf_in_preview_fallbacks_to_exec(monkeypatch: pytest.MonkeyPatch) -> None:
    run_open = _RunRecorder()
    run_open.returncode = 1
    run_open.stderr = "kLSNoExecutableErr"
    exec_spawn = _SpawnRecorder()
    monkeypatch.setattr("cvworkbench.dev.open._run_command", run_open)
    monkeypatch.setattr("cvworkbench.dev.open._spawn_command", exec_spawn)
    monkeypatch.setattr("cvworkbench.dev.open.sys.platform", "darwin")
    monkeypatch.setattr("cvworkbench.dev.open._preview_process_running", lambda: False)
    monkeypatch.setattr(
        "cvworkbench.dev.open._preview_app_path",
        lambda: Path("/Applications/Preview.app"),
    )
    monkeypatch.setattr(
        "cvworkbench.dev.open._app_executable_path",
        lambda path: path / "Contents" / "MacOS" / "Preview",
    )

    result = open_pdf_in_preview(Path("/tmp/cv.pdf"))

    assert result.opened is True
    assert exec_spawn.calls[0] == [
        "/Applications/Preview.app/Contents/MacOS/Preview",
        "/tmp/cv.pdf",
    ]


def test_resolve_preview_viewer_defaults_to_preview_app_on_macos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cvworkbench.dev.open.sys.platform", "darwin")
    monkeypatch.delenv("CVW_PREVIEW_VIEWER", raising=False)

    result = resolve_preview_viewer(None)

    assert result == PreviewViewer.PREVIEW_APP


def test_resolve_preview_viewer_defaults_to_browser_elsewhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cvworkbench.dev.open.sys.platform", "linux")
    monkeypatch.delenv("CVW_PREVIEW_VIEWER", raising=False)

    result = resolve_preview_viewer(None)

    assert result == PreviewViewer.BROWSER
