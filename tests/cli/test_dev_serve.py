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

    assert result.exit_code == 0
    assert "opened_browser: false" in result.stdout
    assert "WARN:" in result.stderr
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
