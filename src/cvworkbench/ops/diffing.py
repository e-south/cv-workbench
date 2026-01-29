"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/diffing.py

Computes diffs between generated artifacts.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cvworkbench.config import (
    resolve_default_variant,
    resolve_dist_path,
    resolve_runs_path,
    resolve_variant_path,
)
from cvworkbench.build.paths import output_path
from cvworkbench.variants import load_variant


class DiffError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArtifactSpec:
    kind: str
    format: str | None = None


@dataclass(frozen=True)
class DiffSelection:
    artifact: ArtifactSpec
    run: str | None
    variant: str | None


def diff_artifacts(
    *,
    config_path: Path,
    selection_a: DiffSelection,
    selection_b: DiffSelection,
) -> tuple[str, dict[str, Any]]:
    path_a = _resolve_artifact_path(config_path, selection_a)
    path_b = _resolve_artifact_path(config_path, selection_b)

    text_a = _read_artifact(path_a, selection_a.artifact.kind)
    text_b = _read_artifact(path_b, selection_b.artifact.kind)

    diff_lines = _unified_diff(text_a, text_b, path_a, path_b)
    diff_text = "\n".join(diff_lines)

    summary = _build_summary(
        selection_a,
        selection_b,
        path_a,
        path_b,
        diff_lines,
    )
    return diff_text, summary


def parse_artifact(spec: str | None) -> ArtifactSpec:
    if not spec:
        return ArtifactSpec(kind="rendered", format=None)
    if ":" in spec:
        kind, fmt = spec.split(":", 1)
        return ArtifactSpec(kind=kind.strip(), format=fmt.strip())
    return ArtifactSpec(kind=spec.strip(), format=None)


def _resolve_artifact_path(config_path: Path, selection: DiffSelection) -> Path:
    artifact = selection.artifact
    if artifact.kind == "rendered":
        if selection.run:
            raise DiffError("rendered artifacts do not support --run")
        variant_id = selection.variant or resolve_default_variant(config_path)
        variant_path = resolve_variant_path(variant_id, config_path)
        variant = load_variant(variant_path)
        render_format = artifact.format or "md"
        if render_format not in variant.outputs:
            raise DiffError(f"Variant '{variant.id}' does not include output {render_format}")
        dist_dir = resolve_dist_path(config_path) / variant.id
        return output_path(dist_dir, variant, render_format)

    run_dir = _resolve_run_dir(config_path, selection.run)
    if artifact.kind == "canonical":
        if artifact.format:
            raise DiffError("canonical artifact does not support formats")
        return run_dir / "canonical.md"
    if artifact.kind == "resume":
        if artifact.format:
            raise DiffError("resume artifact does not support formats")
        return run_dir / "resume.json"

    raise DiffError(f"Unknown artifact type: {artifact.kind}")


def _resolve_run_dir(config_path: Path, run: str | None) -> Path:
    runs_root = resolve_runs_path(config_path)
    if run:
        candidate = Path(run)
        if candidate.exists():
            return candidate
        candidate = runs_root / run
        if candidate.exists():
            return candidate
        raise DiffError(f"Run not found: {run}")

    if not runs_root.exists():
        raise DiffError("Runs directory not found")

    runs = [path for path in runs_root.iterdir() if path.is_dir()]
    if not runs:
        raise DiffError("No runs available")
    return sorted(runs)[-1]


def _read_artifact(path: Path, kind: str) -> str:
    if not path.exists():
        raise DiffError(f"Artifact not found: {path}")
    if kind == "resume":
        payload = json.loads(path.read_text())
        return json.dumps(payload, indent=2, sort_keys=True)
    return path.read_text()


def _unified_diff(text_a: str, text_b: str, path_a: Path, path_b: Path) -> list[str]:
    from difflib import unified_diff

    lines_a = text_a.splitlines()
    lines_b = text_b.splitlines()
    return list(
        unified_diff(
            lines_a,
            lines_b,
            fromfile=str(path_a),
            tofile=str(path_b),
            lineterm="",
        )
    )


def _build_summary(
    selection_a: DiffSelection,
    selection_b: DiffSelection,
    path_a: Path,
    path_b: Path,
    diff_lines: list[str],
) -> dict[str, Any]:
    additions = 0
    deletions = 0
    for line in diff_lines:
        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1

    return {
        "a": {
            "path": str(path_a),
            "artifact": selection_a.artifact.kind,
        },
        "b": {
            "path": str(path_b),
            "artifact": selection_b.artifact.kind,
        },
        "equal": additions == 0 and deletions == 0,
        "additions": additions,
        "deletions": deletions,
    }
