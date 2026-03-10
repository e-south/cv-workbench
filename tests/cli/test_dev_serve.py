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


def test_dev_serve_builds_html() -> None:
    html_path = Path("var/dist/base/cv.html")
    if html_path.exists():
        html_path.unlink()

    runner = CliRunner()
    env = os.environ.copy()
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
    )

    assert result.exit_code == 1
    assert "Address already in use" in result.stderr
    assert "uv run cvw dev stop" in result.stderr


def test_dev_serve_rejects_legacy_preview_env() -> None:
    runner = CliRunner()
    env = os.environ.copy()
    env["CVW_SKIP_OPEN"] = "1"

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
        env=env,
    )

    assert result.exit_code == 2
    assert "legacy preview environment" in result.stderr


def test_dev_serve_rejects_legacy_flag() -> None:
    runner = CliRunner()

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
    )

    assert result.exit_code == 2
    assert "--viewer" in result.stderr
