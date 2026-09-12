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


def test_gc_runs_keeps_latest_per_project_and_variant(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    for run_id, day in [
        ("global", 4),
        ("projects/alpha/old", 1),
        ("projects/alpha/current", 2),
        ("projects/beta/current", 3),
    ]:
        _write_run(tmp_path, run_id, f"2026-01-0{day}T00:00:00+00:00", "base")

    summary = gc_runs(
        config_path=config, keep_latest=1, keep=[], include_invalid=False, confirm=False
    )

    assert [item.run_id for item in summary.candidates] == ["projects/alpha/old"]
    assert {item.run_id for item in summary.kept} == {
        "global",
        "projects/alpha/current",
        "projects/beta/current",
    }


@pytest.mark.parametrize("run_id", ["damaged", "projects/alpha/damaged"])
def test_gc_runs_keeps_explicit_invalid_run(tmp_path: Path, run_id: str) -> None:
    config = _write_config(tmp_path)
    kept = tmp_path / "var" / "runs" / run_id
    kept.mkdir(parents=True)
    (kept / "notes.md").write_text("Keep for recovery")
    removable = tmp_path / "var" / "runs" / "unneeded"
    removable.mkdir()

    preview = gc_runs(
        config_path=config, keep_latest=0, keep=[run_id], include_invalid=True, confirm=False
    )
    assert preview.invalid_candidates == [removable]
    assert preview.keep_reasons[run_id] == ["explicit_keep"]
    result = gc_runs(
        config_path=config, keep_latest=0, keep=[run_id], include_invalid=True, confirm=True
    )
    assert result.removed == 1
    assert (kept / "notes.md").read_text() == "Keep for recovery"
    assert not removable.exists()


@pytest.mark.parametrize("confirm", [False, True])
def test_gc_runs_rejects_outside_root_through_python_api(tmp_path: Path, confirm: bool) -> None:
    config = _write_config(tmp_path)
    run = _write_run(tmp_path, "source", "2026-01-01T00:00:00+00:00", "base")
    external = tmp_path / "outside"
    external.mkdir()
    relocated = external / "source"
    run.rename(relocated)
    config.write_text("paths:\n  runs: ../outside\n")

    with pytest.raises(RunError, match="runs root"):
        gc_runs(config_path=config, keep_latest=0, keep=[], include_invalid=True, confirm=confirm)
    assert (relocated / "manifest.json").is_file()


@pytest.mark.parametrize("confirm", [False, True])
def test_gc_runs_preflights_symlink_ancestors_before_deletion(
    tmp_path: Path, confirm: bool
) -> None:
    config = _write_config(tmp_path)
    first = _write_run(tmp_path, "first", "2026-01-01T00:00:00+00:00", "base")
    external_run = _write_run(tmp_path / "outside", "source", "2026-01-02T00:00:00+00:00", "base")
    project_root = tmp_path / "var" / "runs" / "projects"
    project_root.mkdir()
    (project_root / "linked").symlink_to(external_run.parent, target_is_directory=True)

    with pytest.raises(RunError, match="Run cleanup path"):
        gc_runs(config_path=config, keep_latest=0, keep=[], include_invalid=True, confirm=confirm)
    assert (first / "manifest.json").is_file()
    assert (external_run / "manifest.json").is_file()


def test_gc_runs_rejects_absolute_symlink_root_even_when_empty(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    external = tmp_path / "outside"
    external.mkdir()
    linked = tmp_path / "var" / "linked"
    linked.parent.mkdir()
    linked.symlink_to(external, target_is_directory=True)
    config.write_text(f"paths:\n  runs: {linked}\n")

    with pytest.raises(RunError, match="runs root"):
        gc_runs(config_path=config, keep_latest=1, keep=[], include_invalid=False, confirm=False)
