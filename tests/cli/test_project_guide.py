"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_project_guide.py

Tests project guide command behavior.

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


def test_project_guide_creates_project_and_recommends_variants(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    job_path = tmp_path / "job.txt"
    job_path.write_text("Leadership and reliability focus.\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "guide",
            "--job-file",
            str(job_path),
            "--sot-path",
            "sot.sample",
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "project.guide"
    assert payload["project"]["project_dir"].endswith("var/projects/job")
    assert payload["recommendations"]
