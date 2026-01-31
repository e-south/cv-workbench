"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_runs_gc.py

Tests run garbage collection behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cvworkbench.ops.runs import RunError, gc_runs


def _write_config(root: Path) -> Path:
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  runs: ../var/runs",
            ]
        )
        + "\n"
    )
    return config_path


def _write_run(root: Path, run_id: str, created_at: str, variant_id: str) -> Path:
    run_dir = root / "var" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created_at": created_at,
        "formats": ["md"],
        "outputs": {"md": "cv.md"},
        "variant": {"id": variant_id},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return run_dir


def test_gc_runs_keeps_latest_per_variant(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    old_run = _write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        "2026-01-01T00:00:00+00:00",
        "base",
    )
    _write_run(
        tmp_path,
        "2026-01-02T00-00-00Z",
        "2026-01-02T00:00:00+00:00",
        "base",
    )
    _write_run(
        tmp_path,
        "2026-01-03T00-00-00Z",
        "2026-01-03T00:00:00+00:00",
        "cover",
    )

    summary = gc_runs(
        config_path=config_path,
        keep_latest=1,
        keep=[],
        include_invalid=False,
        confirm=False,
    )

    assert summary.status == "dry_run"
    assert [candidate.run_id for candidate in summary.candidates] == ["2026-01-01T00-00-00Z"]

    summary = gc_runs(
        config_path=config_path,
        keep_latest=1,
        keep=[],
        include_invalid=False,
        confirm=True,
    )
    assert summary.status == "cleaned"
    assert summary.removed == 1
    assert not old_run.exists()


def test_gc_runs_respects_keep_list(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        "2026-01-01T00:00:00+00:00",
        "base",
    )
    _write_run(
        tmp_path,
        "2026-01-02T00-00-00Z",
        "2026-01-02T00:00:00+00:00",
        "base",
    )

    summary = gc_runs(
        config_path=config_path,
        keep_latest=1,
        keep=["2026-01-01T00-00-00Z"],
        include_invalid=False,
        confirm=False,
    )

    assert summary.status == "empty"
    assert not summary.candidates


def test_gc_runs_requires_known_keep_ids(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        "2026-01-01T00:00:00+00:00",
        "base",
    )

    with pytest.raises(RunError, match="Unknown run id"):
        gc_runs(
            config_path=config_path,
            keep_latest=1,
            keep=["missing"],
            include_invalid=False,
            confirm=False,
        )
