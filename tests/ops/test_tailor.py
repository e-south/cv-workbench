"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_tailor.py

Tests tailor command scaffolding.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from cvworkbench.cli import app


def test_tailor_writes_draft_files(tmp_path: Path) -> None:
    job_path = tmp_path / "job.md"
    job_path.write_text("Sample job description.\n")

    output_dir = tmp_path / "drafts" / "sample-role"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "tailor",
            "--job",
            str(job_path),
            "--base-variant",
            "base",
            "--out",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert (output_dir / "job.md").exists()
    assert (output_dir / "variant.yaml").exists()
    assert (output_dir / "patch.diff").exists()
    assert (output_dir / "prompt.json").exists()
    assert (output_dir / "signals.json").exists()

    variant_data = yaml.safe_load((output_dir / "variant.yaml").read_text())
    assert variant_data["variant"]["id"] == "sample-role"

    signals = yaml.safe_load((output_dir / "signals.json").read_text())
    assert "keywords" in signals
    assert "sample" in signals["keywords"]
    assert "job" in signals["keywords"]
