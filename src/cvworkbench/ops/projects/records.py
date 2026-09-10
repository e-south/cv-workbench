"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/records.py

Define project artifact records, patch vocabulary, and record timestamps.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


class ProjectError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProjectPaths:
    project_dir: Path
    project_file: Path
    job_dir: Path
    extracted_path: Path
    signals_path: Path
    raw_path: Path | None
    variant_path: Path
    patch_path: Path


@dataclass(frozen=True)
class ProjectManifest:
    """One file read, with original bytes and its independently mutable document."""

    source_bytes: bytes = field(repr=False)
    document: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class ProjectSpec:
    project_id: str
    project_dir: Path
    base_variant_id: str
    variant_path: Path
    patch_path: Path
    sot_path: Path


@dataclass(frozen=True)
class ProjectSummary:
    project_id: str
    project_dir: Path
    base_variant_id: str
    created_at: str | None
    job_source: str | None
    metadata_errors: tuple[str, ...]


@dataclass(frozen=True)
class ProjectJobSource:
    kind: Literal["file", "url"]
    value: str


@dataclass(frozen=True)
class ProjectArtifactMetadata:
    path: Path
    recorded_sha256: str


@dataclass(frozen=True)
class ProjectMetadata:
    created_at: str
    source: ProjectJobSource
    extracted: ProjectArtifactMetadata
    raw_path: Path | None
    signals: ProjectArtifactMetadata


ProjectArtifactState = Literal["matches_record", "changed", "missing", "unreadable"]


@dataclass(frozen=True)
class ProjectArtifactCheck:
    name: Literal["extracted_text", "signals"]
    path: Path
    state: ProjectArtifactState
    recorded_sha256: str
    observed_sha256: str | None
    error: str | None = None


@dataclass(frozen=True)
class GuidanceJobInputs:
    text: str = field(repr=False)
    signals: dict[str, Any] = field(repr=False)
    extracted_sha256: str
    signals_sha256: str


@dataclass(frozen=True)
class GuidanceInputCheck:
    state: Literal["matches_inputs", "changed", "unverifiable"]
    changed: tuple[str, ...] = ()
    unavailable: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectProposalIssue:
    artifact: Literal["variant", "patch"]
    state: Literal["missing", "unreadable", "invalid"]
    error: str


@dataclass(frozen=True)
class ProjectDetails:
    spec: ProjectSpec
    created_at: str
    job_source_type: str
    job_source_value: str
    extracted_path: Path
    raw_path: Path | None
    signals_path: Path
    signals_hash: str
    proposal_variant_id: str | None
    proposal_document_type: str | None
    patch_format: str | None
    patch_is_empty: bool | None
    patch_line_count: int | None
    patch_operations: tuple[str, ...] | None
    artifact_checks: tuple[ProjectArtifactCheck, ...] = ()
    proposal_issues: tuple[ProjectProposalIssue, ...] = ()

    @property
    def proposal_available(self) -> bool:
        return (
            self.proposal_variant_id is not None
            and self.patch_format is not None
            and not self.proposal_issues
        )


@dataclass(frozen=True)
class ProjectPatch:
    format: str
    diff: str
    operations: tuple[dict[str, Any], ...]


_PROJECT_PATCH_FORMAT_OPS = "project-ops"


_PROJECT_OP_REPLACE_EXPERIENCE_BULLET = "replace-experience-bullet"


_PROJECT_OP_REPLACE_PROJECT_SUMMARY = "replace-project-summary"


_PROJECT_OPS_RESUME_SURFACE = frozenset(
    {
        _PROJECT_OP_REPLACE_EXPERIENCE_BULLET,
        _PROJECT_OP_REPLACE_PROJECT_SUMMARY,
    }
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
