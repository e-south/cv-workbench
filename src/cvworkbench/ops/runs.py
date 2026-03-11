"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/runs.py

Summarizes and resolves build run metadata.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from cvworkbench.config import resolve_runs_path


class RunError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    path: Path
    created_at: datetime
    variant_id: str
    formats: list[str]
    outputs: dict[str, str]


@dataclass(frozen=True)
class RunCatalog:
    runs: list[RunInfo]
    invalid: list[Path]


@dataclass(frozen=True)
class RunGcCandidate:
    run_id: str
    path: Path
    variant_id: str
    created_at: datetime
    reason: str


@dataclass(frozen=True)
class RunGcSummary:
    candidates: list[RunGcCandidate]
    kept: list[RunInfo]
    invalid: list[Path]
    removed: int
    status: str


def scan_runs(
    config_path: Path,
    *,
    strict: bool = False,
    include_project_runs: bool = True,
) -> RunCatalog:
    runs_root = resolve_runs_path(config_path)
    if not runs_root.exists():
        return RunCatalog(runs=[], invalid=[])

    runs: list[RunInfo] = []
    invalid: list[Path] = []
    for path in _iter_run_dirs(runs_root, include_project_runs=include_project_runs):
        manifest_path = path / "manifest.json"
        if not manifest_path.exists():
            invalid.append(path)
            continue
        try:
            run = _parse_manifest(manifest_path, run_id=_run_id(runs_root, path))
        except RunError:
            invalid.append(path)
            continue
        runs.append(run)

    if strict and invalid:
        names = ", ".join(path.name for path in invalid)
        raise RunError(f"Run manifests missing or invalid: {names}")

    return RunCatalog(runs=runs, invalid=invalid)


def _iter_run_dirs(runs_root: Path, *, include_project_runs: bool = True) -> list[Path]:
    run_dirs: list[Path] = []
    for path in sorted(runs_root.iterdir()):
        if not path.is_dir():
            continue
        if path.name == "preview":
            continue
        if path.name == "projects":
            if not include_project_runs:
                continue
            for project_dir in sorted(path.iterdir()):
                if not project_dir.is_dir():
                    continue
                for run_dir in sorted(project_dir.iterdir()):
                    if run_dir.is_dir():
                        run_dirs.append(run_dir)
            continue
        run_dirs.append(path)
    return run_dirs


def _run_id(runs_root: Path, run_dir: Path) -> str:
    return run_dir.relative_to(runs_root).as_posix()


def _run_is_project_scoped(run: RunInfo) -> bool:
    return run.run_id.startswith("projects/")


def group_runs_by_variant(runs: list[RunInfo]) -> dict[str, list[RunInfo]]:
    ordered = sorted(runs, key=lambda run: run.created_at, reverse=True)
    grouped: dict[str, list[RunInfo]] = {}
    for run in ordered:
        grouped.setdefault(run.variant_id, []).append(run)
    return grouped


def latest_runs_by_variant(
    config_path: Path,
    *,
    limit: int = 3,
    include_project_runs: bool = False,
) -> tuple[dict[str, list[RunInfo]], list[Path]]:
    catalog = scan_runs(config_path, strict=False, include_project_runs=True)
    runs = catalog.runs
    if not include_project_runs:
        runs = [run for run in runs if not _run_is_project_scoped(run)]
    grouped = group_runs_by_variant(runs)
    trimmed = {variant: runs[:limit] for variant, runs in grouped.items()}
    return trimmed, catalog.invalid


def resolve_latest_run(
    config_path: Path,
    variant_id: str | None = None,
    *,
    include_project_runs: bool = False,
) -> RunInfo:
    catalog = scan_runs(config_path, strict=False, include_project_runs=True)
    if not catalog.runs:
        if catalog.invalid:
            names = ", ".join(path.name for path in catalog.invalid)
            raise RunError(f"No valid runs available; run manifests missing or invalid: {names}")
        raise RunError("No runs available")

    runs = catalog.runs
    if not include_project_runs:
        runs = [run for run in runs if not _run_is_project_scoped(run)]
    if variant_id:
        variant_runs = [run for run in catalog.runs if run.variant_id == variant_id]
        if include_project_runs:
            runs = variant_runs
        else:
            runs = [run for run in variant_runs if not _run_is_project_scoped(run)]
        if not runs:
            if variant_runs and not include_project_runs:
                raise RunError(
                    f"No non-project runs available for variant: {variant_id}; "
                    "use --project <project-id> or --run <run-id>"
                )
            raise RunError(f"No runs available for variant: {variant_id}")
    elif not runs:
        raise RunError("No non-project runs available")

    return sorted(runs, key=lambda run: run.created_at, reverse=True)[0]


def resolve_latest_project_run(
    config_path: Path,
    project_id: str,
    *,
    variant_id: str | None = None,
) -> RunInfo:
    catalog = scan_runs(config_path, strict=False)
    prefix = f"projects/{project_id}/"
    runs = [run for run in catalog.runs if run.run_id.startswith(prefix)]
    if not runs:
        raise RunError(f"No runs available for project: {project_id}")
    if variant_id:
        runs = [run for run in runs if run.variant_id == variant_id]
        if not runs:
            raise RunError(f"No runs available for project {project_id} and variant: {variant_id}")
    return sorted(runs, key=lambda run: run.created_at, reverse=True)[0]


def resolve_run(config_path: Path, run: str | Path) -> RunInfo:
    runs_root = resolve_runs_path(config_path)
    candidate = Path(run)
    run_dir: Path | None = None

    if candidate.exists():
        run_dir = candidate if candidate.is_dir() else candidate.parent
    else:
        repo_relative = runs_root / str(run)
        if repo_relative.exists():
            run_dir = repo_relative if repo_relative.is_dir() else repo_relative.parent

    if run_dir is None:
        raise RunError(f"Run not found: {run}")

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise RunError(f"Run manifest not found: {manifest_path}")

    try:
        run_id = _run_id(runs_root, run_dir)
    except ValueError:
        run_id = run_dir.name
    return _parse_manifest(manifest_path, run_id=run_id)


def _parse_manifest(manifest_path: Path, run_id: str) -> RunInfo:
    try:
        raw = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        raise RunError(f"Run manifest is invalid: {manifest_path}") from exc
    if not isinstance(raw, dict):
        raise RunError(f"Run manifest is invalid: {manifest_path}")

    created_at_value = raw.get("created_at")
    created_at = _parse_timestamp(created_at_value, manifest_path)
    formats = _require_list(raw, "formats", manifest_path)
    outputs = _require_outputs(raw.get("outputs"), manifest_path)
    variant_data = raw.get("variant")
    if not isinstance(variant_data, dict):
        raise RunError(f"Run manifest missing variant data: {manifest_path}")
    variant_id = _require_str(variant_data, "id", manifest_path)

    return RunInfo(
        run_id=run_id,
        path=manifest_path.parent,
        created_at=created_at,
        variant_id=variant_id,
        formats=formats,
        outputs=outputs,
    )


def gc_runs(
    *,
    config_path: Path,
    keep_latest: int,
    keep: list[str],
    include_invalid: bool,
    confirm: bool,
) -> RunGcSummary:
    if keep_latest < 0:
        raise RunError("keep_latest must be zero or greater")

    catalog = scan_runs(config_path, strict=False)
    runs = catalog.runs
    invalid = catalog.invalid

    if not runs and not invalid:
        return RunGcSummary(candidates=[], kept=[], invalid=[], removed=0, status="empty")

    run_by_id = {run.run_id: run for run in runs}
    invalid_ids = {path.name for path in invalid}
    unknown = [run_id for run_id in keep if run_id not in run_by_id and run_id not in invalid_ids]
    if unknown:
        raise RunError(f"Unknown run id(s): {', '.join(sorted(unknown))}")

    keep_ids = set(keep)
    kept_by_latest: set[str] = set()
    grouped = group_runs_by_variant(runs)
    for variant_runs in grouped.values():
        for run in variant_runs[:keep_latest]:
            kept_by_latest.add(run.run_id)

    kept_ids = keep_ids | kept_by_latest
    candidates: list[RunGcCandidate] = []
    kept: list[RunInfo] = []
    for run in runs:
        if run.run_id in kept_ids:
            kept.append(run)
            continue
        candidates.append(
            RunGcCandidate(
                run_id=run.run_id,
                path=run.path,
                variant_id=run.variant_id,
                created_at=run.created_at,
                reason="older_than_keep_latest",
            )
        )

    candidates.sort(key=lambda item: item.created_at)
    kept.sort(key=lambda item: item.created_at, reverse=True)

    if not candidates and not (include_invalid and invalid):
        return RunGcSummary(
            candidates=[],
            kept=kept,
            invalid=invalid,
            removed=0,
            status="empty",
        )

    if not confirm:
        return RunGcSummary(
            candidates=candidates,
            kept=kept,
            invalid=invalid,
            removed=0,
            status="dry_run",
        )

    removed = 0
    for candidate in candidates:
        _remove_run_dir(candidate.path)
        removed += 1
    if include_invalid:
        for path in invalid:
            _remove_run_dir(path)
            removed += 1

    return RunGcSummary(
        candidates=candidates,
        kept=kept,
        invalid=invalid,
        removed=removed,
        status="cleaned",
    )


def _parse_timestamp(value: object, manifest_path: Path) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise RunError(f"Run manifest missing created_at: {manifest_path}")
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise RunError(f"Run manifest created_at is invalid: {manifest_path}") from exc


def _require_str(data: dict[str, Any], key: str, manifest_path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RunError(f"Run manifest missing {key}: {manifest_path}")
    return value.strip()


def _require_list(data: dict[str, Any], key: str, manifest_path: Path) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise RunError(f"Run manifest missing {key}: {manifest_path}")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise RunError(f"Run manifest invalid {key}: {manifest_path}")
        items.append(item.strip())
    return items


def _require_outputs(value: object, manifest_path: Path) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise RunError(f"Run manifest missing outputs: {manifest_path}")
    outputs: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise RunError(f"Run manifest invalid outputs: {manifest_path}")
        if not isinstance(item, str) or not item.strip():
            raise RunError(f"Run manifest invalid outputs: {manifest_path}")
        outputs[key] = item.strip()
    return outputs


def _remove_run_dir(path: Path) -> None:
    if not path.exists():
        raise RunError(f"Run path not found: {path}")
    if not path.is_dir():
        raise RunError(f"Run path is not a directory: {path}")
    shutil.rmtree(path)
