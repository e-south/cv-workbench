"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_status.py

Tests status command output.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


def _write_config(root: Path) -> Path:
    config_dir = root / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md, pdf]",
                "  document_type: resume",
            ]
        )
        + "\n"
    )
    (variants_dir / "cover.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: cover",
                "  outputs: [md]",
                "  document_type: cover-letter",
                "  include_tags: [leadership]",
            ]
        )
        + "\n"
    )
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: ../var/dist",
                "  runs: ../var/runs",
                "  reviews: ../var/reviews",
                "  projects: ../var/projects",
                "variant_lifecycle:",
                "  ttl_days: 7",
                "variants:",
                "  default: base",
            ]
        )
        + "\n"
    )
    return config_path


def _write_run(root: Path, run_id: str, created_at: str, variant_id: str) -> None:
    run_dir = root / "var" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created_at": created_at,
        "formats": ["md"],
        "outputs": {"md": "cv.md"},
        "variant": {"id": variant_id},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


def _write_project(root: Path) -> None:
    project_dir = root / "var" / "projects" / "job-1"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: job-1",
                "  created_at: 2026-01-01T00:00:00+00:00",
                "  base_variant: base",
                "  sot_path: /tmp/sot",
                "  job:",
                "    source:",
                "      type: file",
                "      value: /tmp/job.txt",
                "    extracted_path: job/extracted.txt",
                "    extracted_hash: hash",
                "    raw_path: null",
                "  signals:",
                "    path: job/signals.json",
                "    hash: hash",
            ]
        )
        + "\n"
    )


def _write_review(root: Path) -> None:
    review_dir = root / "var" / "reviews" / "base"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "cv.docx").write_bytes(b"docx")
    (review_dir / "cv.pdf").write_bytes(b"pdf")


def test_status_json_reports_runs_variants_and_projects(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_run(tmp_path, "2026-01-02T00-00-00Z", "2026-01-02T00:00:00+00:00", "base")
    _write_run(tmp_path, "2026-01-03T00-00-00Z", "2026-01-03T00:00:00+00:00", "base")
    _write_run(tmp_path, "2026-01-04T00-00-00Z", "2026-01-04T00:00:00+00:00", "cover")
    _write_project(tmp_path)
    _write_review(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "status",
            "--json",
            "--sot-path",
            "sot.sample",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "status"
    assert payload["variants"]["config_count"] == 2
    assert payload["projects"]["count"] == 1
    assert payload["reviews"]["count"] == 1
    recents = payload["runs"]["recents_by_variant"]["base"]
    assert recents[0]["run_id"] == "2026-01-03T00-00-00Z"
