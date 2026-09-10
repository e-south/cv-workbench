"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/artifacts.py

Compare stored job artifacts with recorded hashes without requiring live proposals.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import Literal

from cvworkbench.ops.projects.manifest import (
    _project_metadata,
    _project_relative_path,
    load_project_metadata,
)
from cvworkbench.ops.projects.records import (
    GuidanceJobInputs,
    ProjectArtifactCheck,
    ProjectArtifactMetadata,
    ProjectArtifactState,
    ProjectError,
    ProjectMetadata,
    ProjectPaths,
)


def capture_guidance_job_inputs(paths: ProjectPaths) -> GuidanceJobInputs:
    """Parse and fingerprint the same captured job bytes for guidance."""
    try:
        text_bytes = _regular_artifact(
            paths.project_dir, paths.extracted_path, "extracted_text"
        ).read_bytes()
        signals_bytes = _regular_artifact(
            paths.project_dir, paths.signals_path, "signals"
        ).read_bytes()
    except OSError as exc:
        raise ProjectError("Stored guidance job inputs could not be read") from exc
    try:
        text = text_bytes.decode("utf-8")
        signals = json.loads(signals_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectError("Guidance requires UTF-8 job text and valid signals JSON") from exc
    if not isinstance(signals, dict):
        raise ProjectError("Guidance signals must be a JSON object")
    return GuidanceJobInputs(
        text=text,
        signals=signals,
        extracted_sha256=hashlib.sha256(text_bytes).hexdigest(),
        signals_sha256=hashlib.sha256(signals_bytes).hexdigest(),
    )


def _regular_artifact(project_dir: Path, path: Path, name: str) -> Path:
    resolved = _project_relative_path(project_dir, str(path), name)
    if not stat.S_ISREG(resolved.stat().st_mode):
        raise ProjectError(f"Stored {name} artifact must be a regular file")
    return resolved


def inspect_project_artifacts(project_dir: Path) -> tuple[ProjectArtifactCheck, ...]:
    """Check recorded job files independently of proposal and review readiness."""
    data = load_project_metadata(project_dir)
    return _inspect_project_artifacts(project_dir, _project_metadata(project_dir, data))


def _inspect_project_artifacts(
    project_dir: Path, metadata: ProjectMetadata
) -> tuple[ProjectArtifactCheck, ...]:
    return (
        _inspect_artifact(project_dir, "extracted_text", metadata.extracted),
        _inspect_artifact(project_dir, "signals", metadata.signals),
    )


def _inspect_artifact(
    project_dir: Path,
    name: Literal["extracted_text", "signals"],
    metadata: ProjectArtifactMetadata,
) -> ProjectArtifactCheck:
    state: ProjectArtifactState
    observed = None
    error = None
    try:
        path = _regular_artifact(project_dir, metadata.path, name)
        with path.open("rb") as handle:
            observed = hashlib.file_digest(handle, "sha256").hexdigest()
        state = "matches_record" if observed == metadata.recorded_sha256.lower() else "changed"
    except FileNotFoundError:
        state = "missing"
        error = f"Stored {name} artifact is missing"
    except ProjectError as exc:
        state = "unreadable"
        error = str(exc)
    except OSError:
        state = "unreadable"
        error = f"Stored {name} artifact could not be read"
    return ProjectArtifactCheck(
        name=name,
        path=metadata.path,
        state=state,
        recorded_sha256=metadata.recorded_sha256,
        observed_sha256=observed,
        error=error,
    )
