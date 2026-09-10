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
import stat
from pathlib import Path
from typing import Literal

from cvworkbench.ops.projects.manifest import (
    _project_metadata,
    _project_relative_path,
    load_project_metadata,
)
from cvworkbench.ops.projects.records import (
    ProjectArtifactCheck,
    ProjectArtifactMetadata,
    ProjectArtifactState,
    ProjectError,
    ProjectMetadata,
)


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
        path = _project_relative_path(project_dir, str(metadata.path), name)
        if not stat.S_ISREG(path.stat().st_mode):
            raise ProjectError(f"Stored {name} artifact must be a regular file")
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
