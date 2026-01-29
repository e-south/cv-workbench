"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/test_resume.py

Tests JSON Resume materialization.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path

from cvworkbench.pipeline import build_documents


def test_resume_written_to_run_dir() -> None:
    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=Path("config/workbench.yaml"),
        variant_id="base",
        formats=["md"],
    )

    resume_path = result.run_dir / "resume.json"
    assert resume_path.exists()

    payload = json.loads(resume_path.read_text())
    assert payload["basics"]["name"] == "Alex Example"
    assert payload["work"][0]["name"] == "Acme Systems"
