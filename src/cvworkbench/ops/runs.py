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


def scan_runs(config_path: Path, *, strict: bool = False) -> RunCatalog:
    runs_root = resolve_runs_path(config_path)
    if not runs_root.exists():
        return RunCatalog(runs=[], invalid=[])

    runs: list[RunInfo] = []
    invalid: list[Path] = []
    for path in sorted(runs_root.iterdir()):
        if not path.is_dir():
            continue
        if path.name == "preview":
            continue
        manifest_path = path / "manifest.json"
        if not manifest_path.exists():
            invalid.append(path)
            continue
        try:
            run = _parse_manifest(manifest_path, run_id=path.name)
        except RunError:
            invalid.append(path)
            continue
        runs.append(run)

    if strict and invalid:
        names = ", ".join(path.name for path in invalid)
        raise RunError(f"Run manifests missing or invalid: {names}")

    return RunCatalog(runs=runs, invalid=invalid)


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
) -> tuple[dict[str, list[RunInfo]], list[Path]]:
    catalog = scan_runs(config_path, strict=False)
    grouped = group_runs_by_variant(catalog.runs)
    trimmed = {variant: runs[:limit] for variant, runs in grouped.items()}
    return trimmed, catalog.invalid


def resolve_latest_run(config_path: Path, variant_id: str | None = None) -> RunInfo:
    catalog = scan_runs(config_path, strict=True)
    if not catalog.runs:
        raise RunError("No runs available")

    runs = catalog.runs
    if variant_id:
        runs = [run for run in runs if run.variant_id == variant_id]
        if not runs:
            raise RunError(f"No runs available for variant: {variant_id}")

    return sorted(runs, key=lambda run: run.created_at, reverse=True)[0]


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
