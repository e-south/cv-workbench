"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_compare.py

Tests compare command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import importlib
import json
from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.ops.render_compare import PageVisualDiff, RenderCompareResult
from cvworkbench.ops.runs import RunInfo


def test_compare_command_emits_json_summary(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("cvworkbench.cli.app")
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "workbench.yaml"
    config_path.write_text("paths:\n  runs: ../var/runs\n")

    out_dir = tmp_path / "var" / "compare" / "sample"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.html"
    report_path.write_text("<html></html>")
    summary_path = out_dir / "summary.json"
    summary_path.write_text("{}\n")
    pdf_a = tmp_path / "var" / "runs" / "a" / "cv.pdf"
    pdf_b = tmp_path / "var" / "runs" / "b" / "cv.pdf"
    pdf_a.parent.mkdir(parents=True, exist_ok=True)
    pdf_b.parent.mkdir(parents=True, exist_ok=True)
    pdf_a.write_bytes(b"%PDF-1.4\n")
    pdf_b.write_bytes(b"%PDF-1.4\n")

    def _fake_compare(**kwargs) -> RenderCompareResult:
        return RenderCompareResult(
            out_dir=out_dir,
            report_path=report_path,
            summary_path=summary_path,
            run_a=RunInfo(
                run_id="a",
                path=pdf_a.parent,
                created_at=datetime.fromisoformat("2026-03-12T00:00:00+00:00"),
                variant_id="base",
                formats=["pdf"],
                outputs={"pdf": "cv.pdf"},
            ),
            run_b=RunInfo(
                run_id="b",
                path=pdf_b.parent,
                created_at=datetime.fromisoformat("2026-03-12T00:05:00+00:00"),
                variant_id="base",
                formats=["pdf"],
                outputs={"pdf": "cv.pdf"},
            ),
            pdf_a=pdf_a,
            pdf_b=pdf_b,
            pages=(
                PageVisualDiff(
                    page=1,
                    image_a=None,
                    image_b=None,
                    hash_a=None,
                    hash_b=None,
                    size_a=None,
                    size_b=None,
                    identical=False,
                ),
            ),
            status="different",
        )

    monkeypatch.setattr(app_module, "compare_rendered_pdfs", _fake_compare)

    runner = CliRunner()
    result = runner.invoke(
        app_module.app,
        [
            "compare",
            "--run-a",
            "a",
            "--run-b",
            "b",
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "compare"
    assert payload["status"] == "different"
    assert payload["report"] == str(report_path)
