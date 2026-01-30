"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_dev_serve.py

Tests dev serve command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
import plistlib

from typer.testing import CliRunner

from cvworkbench.cli import app
import importlib
import os


def test_dev_serve_builds_html(tmp_path: Path) -> None:
    html_path = Path("dist/base/cv.html")
    if html_path.exists():
        html_path.unlink()

    runner = CliRunner()
    env = os.environ.copy()
    env["CVW_SKIP_OPEN"] = "1"
    env["CVW_DEV_ONCE"] = "1"

    result = runner.invoke(
        app,
        [
            "dev",
            "serve",
            "--variant",
            "base",
            "--sot-path",
            "sot.sample",
        ],
        env=env,
    )

    assert result.exit_code == 0
    assert html_path.exists()
    assert html_path.stat().st_size > 0


def test_dev_serve_reports_open_failure(monkeypatch) -> None:
    runner = CliRunner()

    def _fake_open(_path: Path) -> tuple[bool, str | None]:
        return False, "open failed"

    app_module = importlib.import_module("cvworkbench.cli.app")
    monkeypatch.setattr(app_module, "_open_in_browser", _fake_open)

    result = runner.invoke(
        app,
        [
            "dev",
            "serve",
            "--variant",
            "base",
            "--sot-path",
            "sot.sample",
            "--plain",
        ],
        env={"CVW_DEV_ONCE": "1"},
    )

    assert result.exit_code != 0
    assert "ERROR: open failed" in result.stderr
    assert "HINT: open" in result.stderr


def test_open_in_browser_uses_custom_command(monkeypatch) -> None:
    app_module = importlib.import_module("cvworkbench.cli.app")
    captured: dict[str, list[str]] = {}

    def _fake_run(args: list[str]) -> tuple[bool, str | None]:
        captured["args"] = args
        return True, None

    monkeypatch.setattr(app_module, "_run_open_command", _fake_run)
    monkeypatch.setenv("CVW_BROWSER", "echo custom-browser")

    opened, error = app_module._open_in_browser("http://example.test")

    assert opened is True
    assert error is None
    assert captured["args"] == ["echo", "custom-browser", "http://example.test"]


def test_open_in_browser_reports_missing_custom_command(monkeypatch) -> None:
    app_module = importlib.import_module("cvworkbench.cli.app")

    def _fake_run(_args: list[str]) -> tuple[bool, str | None]:
        raise FileNotFoundError(2, "No such file or directory", "missing-browser")

    monkeypatch.setattr(app_module, "_run_open_command", _fake_run)
    monkeypatch.setenv("CVW_BROWSER", "missing-browser")

    opened, error = app_module._open_in_browser("http://example.test")

    assert opened is False
    assert error is not None
    assert "missing-browser" in error


def test_open_in_browser_requires_default_handler_on_macos(monkeypatch) -> None:
    app_module = importlib.import_module("cvworkbench.cli.app")
    monkeypatch.setattr(app_module.sys, "platform", "darwin")
    monkeypatch.delenv("CVW_BROWSER", raising=False)
    monkeypatch.delenv("CVW_SKIP_OPEN", raising=False)
    monkeypatch.setattr(app_module, "_macos_default_handler_for_scheme", lambda _: None)

    opened, error = app_module._open_in_browser("http://example.test")

    assert opened is False
    assert error is not None
    assert "default web browser" in error


def test_macos_default_handler_reads_launchservices(monkeypatch, tmp_path: Path) -> None:
    app_module = importlib.import_module("cvworkbench.cli.app")
    plist_path = tmp_path / "launchservices.plist"
    with plist_path.open("wb") as handle:
        plistlib.dump(
            {
                "LSHandlers": [
                    {
                        "LSHandlerURLScheme": "http",
                        "LSHandlerRoleAll": "com.example.browser",
                    }
                ]
            },
            handle,
        )
    monkeypatch.setenv("CVW_LAUNCHSERVICES_PLIST", str(plist_path))

    handler = app_module._macos_default_handler_for_scheme("http")

    assert handler == "com.example.browser"


def test_open_in_browser_uses_macos_app_path(monkeypatch, tmp_path: Path) -> None:
    app_module = importlib.import_module("cvworkbench.cli.app")
    monkeypatch.setattr(app_module.sys, "platform", "darwin")
    monkeypatch.delenv("CVW_BROWSER", raising=False)
    monkeypatch.delenv("CVW_SKIP_OPEN", raising=False)
    monkeypatch.setattr(app_module, "_macos_default_handler_for_scheme", lambda _: "com.example.browser")
    monkeypatch.setattr(app_module, "_macos_browser_app_path", lambda _: tmp_path / "Browser.app")
    monkeypatch.setattr(app_module, "_macos_browser_app_name", lambda _: "Browser")
    captured: dict[str, str] = {}

    def _fake_open(name: str, target: str) -> tuple[bool, str | None]:
        captured["name"] = name
        captured["target"] = target
        return True, None

    monkeypatch.setattr(app_module, "_run_osascript_open", _fake_open)

    opened, error = app_module._open_in_browser("http://example.test")

    assert opened is True
    assert error is None
    assert captured["name"] == "Browser"
    assert captured["target"] == "http://example.test"


def test_open_in_browser_errors_when_macos_executable_missing(monkeypatch) -> None:
    app_module = importlib.import_module("cvworkbench.cli.app")
    monkeypatch.setattr(app_module.sys, "platform", "darwin")
    monkeypatch.delenv("CVW_BROWSER", raising=False)
    monkeypatch.delenv("CVW_SKIP_OPEN", raising=False)
    monkeypatch.setattr(app_module, "_macos_default_handler_for_scheme", lambda _: "com.example.browser")
    monkeypatch.setattr(app_module, "_macos_browser_app_path", lambda _: None)

    opened, error = app_module._open_in_browser("http://example.test")

    assert opened is False
    assert error is not None
    assert "browser app" in error
