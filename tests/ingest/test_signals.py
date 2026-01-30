"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ingest/test_signals.py

Tests evidence spans in signals output.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from cvworkbench.ingestion.signals import build_signals


def test_build_signals_includes_evidence() -> None:
    signals = build_signals("Python AWS experience", source={}, limit=10)

    evidence = signals.get("evidence", {})
    assert "python" in evidence
    spans = evidence["python"]
    assert isinstance(spans, list)
    assert spans[0]["start"] == 0
    assert spans[0]["end"] == 6
