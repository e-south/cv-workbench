"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/records.py

Define project artifact records, patch vocabulary, and record timestamps.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
class ProjectSpec:
    project_id: str
    project_dir: Path
    base_variant_id: str
    variant_path: Path
    patch_path: Path
    sot_path: Path


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
    proposal_variant_id: str
    proposal_document_type: str
    patch_format: str
    patch_is_empty: bool
    patch_line_count: int
    patch_operations: tuple[str, ...]


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
