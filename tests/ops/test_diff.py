"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_diff.py

Tests diff command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app
from tests.utils import strip_ansi


def _write_config(root: Path) -> Path:
    config_dir = root / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text("variant:\n  id: base\n  outputs: [md]\n")
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  runs: ../var/runs",
                "variants:",
                "  default: base",
            ]
        )
        + "\n"
    )
    return config_path


def _write_run(root: Path, run_id: str, canonical: str) -> Path:
    run_dir = root / "var" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "canonical.md").write_text(canonical)
    (run_dir / "resume.json").write_text('{"basics": {"name": "Alpha"}}\n')
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-01-01T00:00:00+00:00",
                "formats": ["md"],
                "outputs": {"md": "cv.md"},
                "variant": {"id": "base"},
                "resume": {"path": "resume.json", "hash": "hash"},
            }
        )
        + "\n"
    )
    return run_dir


def test_diff_resume_json_output() -> None:
    runs_root = Path("var/runs")
    run_a = runs_root / "2026-01-01T00-00-00Z"
    run_b = runs_root / "2026-01-02T00-00-00Z"
    run_a.mkdir(parents=True, exist_ok=True)
    run_b.mkdir(parents=True, exist_ok=True)

    (run_a / "resume.json").write_text('{"basics": {"name": "Alpha"}}\n')
    (run_b / "resume.json").write_text('{"basics": {"name": "Beta"}}\n')

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "diff",
            "--artifact",
            "resume",
            "--run-a",
            str(run_a),
            "--run-b",
            str(run_b),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["equal"] is False
    assert payload["a"]["artifact"] == "resume"


def test_diff_unified_prints_summary() -> None:
    runs_root = Path("var/runs")
    run_a = runs_root / "2026-01-03T00-00-00Z"
    run_b = runs_root / "2026-01-04T00-00-00Z"
    run_a.mkdir(parents=True, exist_ok=True)
    run_b.mkdir(parents=True, exist_ok=True)

    (run_a / "resume.json").write_text('{"basics": {"name": "Alpha"}}\n')
    (run_b / "resume.json").write_text('{"basics": {"name": "Beta"}}\n')

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "diff",
            "--artifact",
            "resume",
            "--run-a",
            str(run_a),
            "--run-b",
            str(run_b),
        ],
    )

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "additions:" in output
    assert "deletions:" in output
    assert "equal:" in output


def test_diff_without_run_ignores_projects_directory(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_run(tmp_path, "2026-01-03T00-00-00Z", "same\n")
    (tmp_path / "var" / "runs" / "projects" / "job").mkdir(parents=True, exist_ok=True)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "diff",
            "--artifact",
            "canonical",
            "--config",
            str(config_path),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["a"]["path"].endswith("2026-01-03T00-00-00Z/canonical.md")
