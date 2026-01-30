"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_dev_serve.py

Tests dev serve command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.dev.open import OpenMode, OpenResult


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
            "--viewer",
            "browser",
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

    def _fake_open(
        _url: str,
        *,
        mode: OpenMode,
        browser: str | None,
    ) -> OpenResult:
        return OpenResult(opened=False, error="open failed", mode=mode)

    app_module = importlib.import_module("cvworkbench.cli.app")
    monkeypatch.setattr(app_module, "_open_url", _fake_open)

    result = runner.invoke(
        app,
        [
            "dev",
            "serve",
            "--viewer",
            "browser",
            "--variant",
            "base",
            "--sot-path",
            "sot.sample",
            "--plain",
        ],
        env={"CVW_DEV_ONCE": "1"},
    )

    assert result.exit_code == 0
    assert "ERROR: open failed" in result.stderr
    assert "HINT: open" in result.stderr


def test_dev_serve_reports_port_in_use(monkeypatch) -> None:
    runner = CliRunner()

    def _fake_serve(*_args, **_kwargs) -> None:
        raise OSError(48, "Address already in use")

    app_module = importlib.import_module("cvworkbench.cli.app")
    monkeypatch.setattr(app_module, "serve_preview", _fake_serve)

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
        env={"CVW_SKIP_OPEN": "1"},
    )

    assert result.exit_code == 1
    assert "Address already in use" in result.stderr
    assert "cvw dev stop" in result.stderr


def test_dev_serve_quicklook_opens_pdf(monkeypatch) -> None:
    runner = CliRunner()
    captured: dict[str, str | OpenMode | None] = {}

    def _fake_open_pdf(path: Path) -> OpenResult:
        captured["url"] = str(path)
        return OpenResult(opened=True, error=None, mode=OpenMode.LAUNCHSERVICES)

    app_module = importlib.import_module("cvworkbench.cli.app")
    monkeypatch.setattr(app_module, "open_pdf", _fake_open_pdf)

    result = runner.invoke(
        app,
        [
            "dev",
            "serve",
            "--viewer",
            "quicklook-pdf",
            "--variant",
            "base",
            "--sot-path",
            "sot.sample",
            "--plain",
        ],
        env={"CVW_DEV_ONCE": "1"},
    )

    assert result.exit_code == 0
    assert str(captured["url"]).endswith("dist/base/cv.pdf")


def test_dev_serve_preview_app_opens_pdf(monkeypatch) -> None:
    runner = CliRunner()
    captured: dict[str, str | OpenMode | None] = {}

    def _fake_open_pdf(path: Path) -> OpenResult:
        captured["url"] = str(path)
        return OpenResult(opened=True, error=None, mode=OpenMode.LAUNCHSERVICES)

    app_module = importlib.import_module("cvworkbench.cli.app")
    monkeypatch.setattr(app_module, "open_pdf_in_preview", _fake_open_pdf)

    result = runner.invoke(
        app,
        [
            "dev",
            "serve",
            "--viewer",
            "preview-app",
            "--variant",
            "base",
            "--sot-path",
            "sot.sample",
            "--plain",
        ],
        env={"CVW_DEV_ONCE": "1"},
    )

    assert result.exit_code == 0
    assert str(captured["url"]).endswith("dist/base/cv.pdf")


def test_dev_serve_viewer_none_skips_open(monkeypatch) -> None:
    runner = CliRunner()
    called = {"count": 0}

    def _fake_open(*_args, **_kwargs) -> OpenResult:
        called["count"] += 1
        return OpenResult(opened=True, error=None, mode=OpenMode.LAUNCHSERVICES)

    app_module = importlib.import_module("cvworkbench.cli.app")
    monkeypatch.setattr(app_module, "_open_url", _fake_open)
    monkeypatch.setattr(app_module, "open_pdf", _fake_open)

    result = runner.invoke(
        app,
        [
            "dev",
            "serve",
            "--viewer",
            "none",
            "--variant",
            "base",
            "--sot-path",
            "sot.sample",
            "--plain",
        ],
        env={"CVW_DEV_ONCE": "1"},
    )

    assert result.exit_code == 0
    assert called["count"] == 0
