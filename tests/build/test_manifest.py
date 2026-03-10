"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_manifest.py

Tests build manifest generation.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path

from cvworkbench.build.pipeline import build_documents


def test_manifest_written() -> None:
    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=Path("config/workbench.yaml"),
        variant_id="base",
        formats=["md"],
    )

    manifest_path = result.dist_dir / "manifest.json"
    assert manifest_path.exists()

    data = json.loads(manifest_path.read_text())
    assert data["variant"]["id"] == "base"
    assert "sot_hashes" in data
    assert data["resume"]["path"] == "resume.json"
    assert "hash" in data["resume"]


def test_manifest_hashes_optional_files() -> None:
    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=Path("config/workbench.yaml"),
        variant_id="base",
        formats=["md"],
    )

    manifest_path = result.dist_dir / "manifest.json"
    data = json.loads(manifest_path.read_text())
    assert "publications.yaml" in data["sot_hashes"]
    assert "honors.yaml" in data["sot_hashes"]


def test_manifest_hashes_snippet_files() -> None:
    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=Path("config/workbench.yaml"),
        variant_id="base",
        formats=["md"],
    )

    manifest_path = result.dist_dir / "manifest.json"
    data = json.loads(manifest_path.read_text())

    assert "snippet_hashes" in data
    assert "snippets/summary.md" in data["snippet_hashes"]


def test_build_writes_render_outputs_to_run_dir() -> None:
    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=Path("config/workbench.yaml"),
        variant_id="base",
        formats=["md"],
    )

    run_output = result.run_dir / "cv.md"
    dist_output = result.dist_dir / "cv.md"

    assert run_output.exists()
    assert run_output.read_text() == dist_output.read_text()
