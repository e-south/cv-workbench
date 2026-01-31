"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_project_flow.py

Tests project creation flow.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

import yaml

from cvworkbench.ingestion.ingest import ExtractResult
from cvworkbench.ops.projects import (
    apply_project_patch,
    create_project_from_file,
    create_project_from_url,
    load_project,
    load_project_patch,
)


def _write_config(root: Path) -> Path:
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    base_variant = {
        "variant": {
            "id": "base",
            "outputs": ["md"],
            "include_tags": [],
            "exclude_tags": [],
        }
    }
    (variants_dir / "base.yaml").write_text(yaml.safe_dump(base_variant, sort_keys=False))
    config_path = config_dir / "workbench.yaml"
    config_path.write_text("paths: {}\n")
    return config_path


def test_create_project_from_url(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True)

    def _fake_extract(url: str, user_agent: str | None) -> ExtractResult:
        return ExtractResult(
            text="Sample job text",
            extractor="mock",
            extractor_version="1.0",
            raw_html="<html></html>",
        )

    monkeypatch.setattr("cvworkbench.ops.projects.fetch_and_extract", _fake_extract)

    result = create_project_from_url(
        url="https://example.com/jobs/1",
        slug="acme",
        base_variant_id="base",
        config_path=config_path,
        sot_path=sot_path,
        store_raw=False,
    )

    project_dir = tmp_path / "var" / "projects" / "acme"
    assert result.project_dir == project_dir
    assert (project_dir / "project.yaml").exists()
    assert (project_dir / "job" / "extracted.txt").read_text() == "Sample job text\n"
    assert not (project_dir / "job" / "raw.html").exists()
    assert (project_dir / "job" / "signals.json").exists()
    assert (project_dir / "proposals" / "variant.yaml").exists()
    assert (project_dir / "proposals" / "patch.yaml").exists()


def test_create_project_from_file(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True)
    job_path = tmp_path / "job.txt"
    job_path.write_text("Job description text")

    result = create_project_from_file(
        job_path=job_path,
        slug="orbit",
        base_variant_id="base",
        config_path=config_path,
        sot_path=sot_path,
        store_raw=False,
    )

    project_dir = tmp_path / "var" / "projects" / "orbit"
    assert result.project_dir == project_dir
    assert (project_dir / "job" / "extracted.txt").read_text() == "Job description text\n"

    spec = load_project(project_dir)
    assert spec.project_id == "orbit"
    assert spec.base_variant_id == "base"
    assert spec.variant_path.exists()

    diff = load_project_patch(project_dir)
    assert diff == ""

    apply_project_patch(project_dir=project_dir, sot_path=sot_path)
