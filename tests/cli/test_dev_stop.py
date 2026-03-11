"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_dev_stop.py

Tests dev stop command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


def _write_config(config_path: Path, runs_path: Path) -> None:
    config_path.write_text(f"paths:\\n  runs: {runs_path.as_posix()}\\n")


def test_dev_stop_errors_without_session(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, tmp_path / "var" / "runs")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["dev", "stop", "--config", str(config_path), "--plain"],
    )

    assert result.exit_code != 0
    assert "Preview session file not found" in result.stderr


def test_dev_stop_removes_session(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    runs_path = tmp_path / "var" / "runs"
    _write_config(config_path, runs_path)
    session_dir = runs_path / "preview"
    session_dir.mkdir(parents=True)
    session_file = session_dir / "session.json"
    session_file.write_text(
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
            }
        )
    )

    app_module = importlib.import_module("cvworkbench.cli.app")
    monkeypatch.setattr(app_module, "_post_preview_stop", lambda *_: (True, None))
    monkeypatch.setattr(app_module, "_wait_for_port_close", lambda *_: True)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["dev", "stop", "--config", str(config_path), "--plain"],
    )

    assert result.exit_code == 0
    assert not session_file.exists()


def test_dev_stop_clears_stale_session_when_api_is_unreachable(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    runs_path = tmp_path / "var" / "runs"
    _write_config(config_path, runs_path)
    session_dir = runs_path / "preview"
    session_dir.mkdir(parents=True)
    session_file = session_dir / "session.json"
    session_file.write_text(
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
    monkeypatch.setattr(app_module, "_post_preview_stop", lambda *_: (False, "connection refused"))
    monkeypatch.setattr(app_module, "_preview_session_conflict", lambda *_: (False, "stale"))

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["dev", "stop", "--config", str(config_path), "--plain"],
    )

    assert result.exit_code == 0
    assert not session_file.exists()
    assert "cleared-stale-session" in result.stdout


def test_dev_stop_force_errors_when_port_is_still_busy_without_live_pid(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.yaml"
    runs_path = tmp_path / "var" / "runs"
    _write_config(config_path, runs_path)
    session_dir = runs_path / "preview"
    session_dir.mkdir(parents=True)
    session_file = session_dir / "session.json"
    session_file.write_text(
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
    monkeypatch.setattr(app_module, "_post_preview_stop", lambda *_: (True, None))
    monkeypatch.setattr(app_module, "_wait_for_port_close", lambda *_: False)
    monkeypatch.setattr(app_module, "_preview_pid_is_live", lambda *_: False)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["dev", "stop", "--config", str(config_path), "--plain", "--force"],
    )

    assert result.exit_code == 1
    assert "Preview port is still in use" in result.stderr
    assert session_file.exists()
