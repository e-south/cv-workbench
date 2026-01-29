"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/test_manifest.py

Tests build manifest generation.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path

from cvworkbench.pipeline import build_documents


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
