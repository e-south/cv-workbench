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
    config_dir = tmp_path / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md]",
            ]
        )
        + "\n"
    )
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  drafts: ../var/drafts",
                "variant_lifecycle:",
                "  ttl_days: 7",
                "variants:",
                "  default: base",
            ]
        )
        + "\n"
    )

    job_path = tmp_path / "job.md"
    job_path.write_text("Sample job description.\n")

    output_dir = tmp_path / "var" / "drafts" / "sample-role"

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
            "--config",
            str(config_path),
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
    assert "evidence" in signals

    prompt = yaml.safe_load((output_dir / "prompt.json").read_text())
    assert prompt["job"]["keywords"][:2] == ["sample", "job"]
    assert {item["keyword"] for item in prompt["signals"]["top_evidence"]} >= {"job", "sample"}
    assert prompt["proposal_plan"]["focus_keywords"][:2] == ["sample", "job"]
