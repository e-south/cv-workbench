"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/runs.py

Inspect build history and determine whether runs contain review inputs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cvworkbench.ops.runs import (
    RunInfo,
    latest_runs_by_variant,
)


def run_payload(run: RunInfo) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "path": str(run.path),
        "created_at": run.created_at.isoformat(),
        "variant_id": run.variant_id,
        "formats": run.formats,
        "outputs": run.outputs,
    }


def runs_summary_line(latest: dict[str, list[dict[str, Any]]]) -> str:
    if not latest:
        return "none"
    lines = []
    for variant_id, runs in latest.items():
        if not runs:
            continue
        lines.append(f"{variant_id}: {runs[0]['run_id']}")
    return "\n".join(lines) if lines else "none"


def runs_recents_line(recents: dict[str, list[dict[str, Any]]]) -> str:
    if not recents:
        return "none"
    lines = []
    for variant_id, runs in recents.items():
        if not runs:
            continue
        run_ids = ", ".join([run["run_id"] for run in runs])
        lines.append(f"{variant_id}: {run_ids}")
    return "\n".join(lines) if lines else "none"


def invalid_runs_line(paths: list[Path]) -> str:
    if not paths:
        return ""
    return ", ".join([path.name for path in paths])


def run_is_review_ready(run: RunInfo | Mapping[str, Any]) -> bool:
    required_formats = {"docx", "pdf"}
    if isinstance(run, RunInfo):
        outputs = run.outputs
        run_path = run.path
    elif isinstance(run, Mapping):
        outputs_value = run.get("outputs")
        path_value = run.get("path")
        if not isinstance(outputs_value, Mapping) or not isinstance(path_value, str):
            return False
        outputs = outputs_value
        run_path = Path(path_value)
    else:
        return False

    run_root = run_path.resolve()
    if not required_formats.issubset(set(outputs.keys())):
        return False
    for fmt in required_formats:
        output_path = outputs.get(fmt)
        if not isinstance(output_path, str) or not output_path.strip():
            return False
        resolved_output = (run_path / output_path).resolve()
        try:
            resolved_output.relative_to(run_root)
        except ValueError:
            return False
        if not resolved_output.exists():
            return False
    selection_path = (run_path / "selection.json").resolve()
    try:
        selection_path.relative_to(run_root)
    except ValueError:
        return False
    return selection_path.exists()


def build_runs_context(
    config_path: Path,
    variants: list[dict[str, Any]],
    *,
    include_recents: bool,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    recents_by_variant, invalid_runs = latest_runs_by_variant(
        config_path,
        limit=3 if include_recents else 1,
        include_project_runs=False,
    )
    variant_ids = [variant["id"] for variant in variants]
    if not variant_ids:
        variant_ids = sorted(recents_by_variant.keys())

    latest_payload: dict[str, list[dict[str, Any]]] = {}
    recents_payload: dict[str, list[dict[str, Any]]] = {}
    for variant_id in variant_ids:
        runs = recents_by_variant.get(variant_id, [])
        payloads = [run_payload(run) for run in runs]
        latest_payload[variant_id] = payloads[:1]
        if include_recents:
            recents_payload[variant_id] = payloads

    section: dict[str, Any] = {
        "latest_summary": runs_summary_line(latest_payload),
        "invalid_summary": invalid_runs_line(invalid_runs),
    }
    if include_recents:
        section.update(
            {
                "latest_by_variant": latest_payload,
                "recents_by_variant": recents_payload,
                "recents_summary": runs_recents_line(recents_payload),
                "invalid": [str(path) for path in invalid_runs],
            }
        )
    return section, latest_payload
