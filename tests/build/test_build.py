"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_build.py

Tests build pipeline behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

import cvworkbench.build.pipeline as pipeline_module
from cvworkbench.cli import app


def test_build_generates_markdown() -> None:
    output_path = Path("var/dist/base/cv.md")
    if output_path.exists():
        output_path.unlink()

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["build", "--variant", "base", "--format", "md", "--sot-path", "sot.sample"],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    content = output_path.read_text()
    assert "Alex Example" in content
    assert ".tag-" not in content


def test_build_marks_publication_roles() -> None:
    output_path = Path("var/dist/base/cv.md")
    if output_path.exists():
        output_path.unlink()

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["build", "--variant", "base", "--format", "md", "--sot-path", "sot.sample"],
    )

    assert result.exit_code == 0
    content = output_path.read_text()
    assert "Alex Example\\*" in content


def test_create_run_dir_adds_suffix_when_timestamp_collides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(pipeline_module, "datetime", FrozenDateTime)

    runs_root = tmp_path / "var" / "runs"
    first = pipeline_module.create_run_dir(runs_root)
    second = pipeline_module.create_run_dir(runs_root)

    assert first.name == "2026-01-01T00-00-00Z"
    assert second.name == "2026-01-01T00-00-00Z-01"
