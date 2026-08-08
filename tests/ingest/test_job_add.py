"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ingest/test_job_add.py

Tests job add ingestion behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import cvworkbench.ingestion.registry as registry_module
from cvworkbench.cli import app
from cvworkbench.ingestion.ingest import ExtractResult
from tests.utils import isolated_filesystem


def _write_minimal_config(root: Path) -> Path:
    config_dir = root / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    workbench = config_dir / "workbench.yaml"
    workbench.write_text(
        "\n".join(
            [
                "paths:",
                "  sot: ../local/sot",
                "  dist: ../var/dist",
                "  runs: ../var/runs",
                "  registry: ../var/registry",
                "variants:",
                "  default: base",
            ]
        )
        + "\n"
    )
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
    return workbench


def test_job_add_creates_registry_entry(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_minimal_config(tmp_path)
    url = "https://example.com/jobs/role"
    expected_id = registry_module.context_id_from_url(url)

    def fake_extract(_url: str, _user_agent: str | None) -> ExtractResult:
        return ExtractResult(text="Sample job text", extractor="test", extractor_version="1.0")

    monkeypatch.setattr(registry_module, "fetch_and_extract", fake_extract)

    runner = CliRunner()
    with isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "job",
                "add",
                "--url",
                url,
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code == 0
    registry_dir = tmp_path / "var" / "registry" / "contexts" / expected_id
    assert (registry_dir / "source.json").exists()
    assert (registry_dir / "extracted.md").read_text() == "Sample job text\n"
    assert (registry_dir / "signals.json").exists()
    assert (registry_dir / "strategy.yaml").exists()

    payload = json.loads((registry_dir / "source.json").read_text())
    assert payload["url"] == url


def test_job_add_rejects_unsafe_url(tmp_path: Path) -> None:
    config_path = _write_minimal_config(tmp_path)

    runner = CliRunner()
    with isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "job",
                "add",
                "--url",
                "http://127.0.0.1/jobs/role",
                "--config",
                str(config_path),
                "--plain",
            ],
        )

    assert result.exit_code != 0
    assert "https" in (result.stderr or "")
