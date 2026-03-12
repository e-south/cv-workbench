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
import json
import os
from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.dev.preview import PreviewSession
from tests.utils import strip_ansi


def _write_preview_config(config_path: Path) -> None:
    variants_dir = config_path.parent / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md, pdf, html]",
            ]
        )
        + "\n"
    )
    themes_dir = Path(__file__).resolve().parents[2] / "build" / "themes"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: ../var/dist",
                "  runs: ../var/runs",
                "variants:",
                "  default: base",
                "render:",
                f"  themes_dir: {themes_dir}",
                "  theme: default",
                "  style_preset: modern",
            ]
        )
        + "\n"
    )


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
    output = strip_ansi((result.stdout or "") + (result.stderr or ""))
    assert "--viewer" in output
    assert "No such option" in output


def test_dev_serve_rejects_live_existing_session(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config" / "workbench.yaml"
    _write_preview_config(config_path)
    session_path = tmp_path / "var" / "runs" / "preview" / "session.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps(
            {
                "pid": 1234,
                "host": "127.0.0.1",
                "port": 8877,
                "url": "http://127.0.0.1:8877/",
                "variant": "base",
                "theme": "default",
                "style_preset": "modern",
                "started_at": "2026-01-31T00:00:00+00:00",
                "session_id": "session-123",
            }
        )
    )

    app_module = importlib.import_module("cvworkbench.cli.app")
    monkeypatch.setattr(
        app_module,
        "_preview_session_conflict",
        lambda *_: (True, "Preview session already running at http://127.0.0.1:8877/"),
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "dev",
            "serve",
            "--variant",
            "base",
            "--sot-path",
            "sot.sample",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 1
    assert "Preview session already running" in result.stderr
    assert "reuse the existing preview URL" in result.stderr


def test_preview_session_conflict_treats_reused_live_pid_without_preview_port_as_stale(
    monkeypatch,
) -> None:
    app_module = importlib.import_module("cvworkbench.cli.app")
    monkeypatch.setattr(
        app_module, "_preview_api_reachable", lambda *_: (False, "connection refused")
    )
    monkeypatch.setattr(app_module, "_preview_pid_is_live", lambda *_: True)
    monkeypatch.setattr(app_module, "_port_is_open", lambda *_: False)

    session = PreviewSession(
        pid=1234,
        host="127.0.0.1",
        port=8877,
        url="http://127.0.0.1:8877/",
        variant_id="base",
        theme_id="default",
        style_preset="modern",
        started_at="2026-01-31T00:00:00+00:00",
    )

    has_conflict, detail = app_module._preview_session_conflict(session)

    assert has_conflict is False
    assert detail == "connection refused"
