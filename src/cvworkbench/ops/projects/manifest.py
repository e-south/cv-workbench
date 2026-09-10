"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/manifest.py

Read project manifests and validate inventory, execution, and descriptive metadata.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from cvworkbench.ops.projects.identity import validate_project_id
from cvworkbench.ops.projects.records import (
    ProjectArtifactMetadata,
    ProjectError,
    ProjectJobSource,
    ProjectManifest,
    ProjectMetadata,
    ProjectSpec,
    ProjectSummary,
)
from cvworkbench.variants import validate_variant_id


def load_project_metadata(project_dir: Path) -> dict[str, Any]:
    """Read manifest identity without requiring retained proposal artifacts."""
    return _read_project_manifest(project_dir).document["project"]


def _read_project_manifest(project_dir: Path) -> ProjectManifest:
    if not project_dir.exists():
        raise ProjectError(f"Project directory not found: {project_dir}")
    project_file = project_dir / "project.yaml"
    if not project_file.exists():
        raise ProjectError(f"Project manifest not found: {project_file}")
    try:
        content = project_file.read_bytes()
        raw = yaml.safe_load(content.decode("utf-8"))
    except (UnicodeError, yaml.YAMLError) as exc:
        raise ProjectError(
            f"Project manifest must contain valid UTF-8 YAML: {project_file}"
        ) from exc
    except OSError as exc:
        raise ProjectError(f"Project manifest could not be read: {project_file}") from exc
    if not isinstance(raw, dict):
        raise ProjectError("Project manifest must be a mapping")
    project_data = raw.get("project")
    if not isinstance(project_data, dict):
        raise ProjectError("Project manifest is invalid")
    validate_project_id(project_data.get("id"))
    base_variant = project_data.get("base_variant")
    if not base_variant:
        raise ProjectError("Project base_variant is required")
    try:
        validate_variant_id(base_variant)
    except ValueError as exc:
        raise ProjectError(f"Project base_variant is invalid: {exc}") from exc
    return ProjectManifest(source_bytes=content, document=raw)


def load_project(project_dir: Path) -> ProjectSpec:
    return _project_spec(project_dir, load_project_metadata(project_dir))


def load_project_summary(project_dir: Path) -> ProjectSummary:
    data = load_project_metadata(project_dir)
    errors: list[str] = []
    created_at = None
    if "created_at" in data:
        try:
            created_at = _project_timestamp(data["created_at"])
        except ProjectError as exc:
            errors.append(str(exc))
    source = None
    if "job" in data:
        try:
            job = _metadata_mapping(data["job"], "job")
            if "source" in job:
                source = _source_summary(job["source"], errors)
        except ProjectError as exc:
            errors.append(str(exc))
    return ProjectSummary(
        project_id=data["id"],
        project_dir=project_dir,
        base_variant_id=data["base_variant"],
        created_at=created_at,
        job_source=source,
        metadata_errors=tuple(errors),
    )


def _source_summary(value: Any, errors: list[str]) -> str | None:
    source = _metadata_mapping(value, "job.source")
    kind = None
    if "type" in source:
        try:
            kind = _source_kind(source["type"])
        except ProjectError as exc:
            errors.append(str(exc))
    if "value" in source:
        try:
            return _metadata_text(source["value"], "job.source.value")
        except ProjectError as exc:
            errors.append(str(exc))
            return None
    return kind


def _project_spec(project_dir: Path, project_data: dict[str, Any]) -> ProjectSpec:
    spec = _project_reference(project_dir, project_data)
    if not spec.variant_path.exists():
        raise ProjectError(f"Project variant not found: {spec.variant_path}")
    if not spec.patch_path.exists():
        raise ProjectError(f"Project patch not found: {spec.patch_path}")
    return spec


def _project_reference(project_dir: Path, project_data: dict[str, Any]) -> ProjectSpec:
    """Resolve recorded identity and locations without requiring proposal files."""
    sot_path_value = project_data.get("sot_path")
    if not isinstance(sot_path_value, str) or not sot_path_value.strip():
        raise ProjectError("Project sot_path is required")
    sot_path = Path(sot_path_value)
    variant_path = project_dir / "proposals" / "variant.yaml"
    patch_path = project_dir / "proposals" / "patch.yaml"
    return ProjectSpec(
        project_id=project_data["id"],
        project_dir=project_dir,
        base_variant_id=project_data["base_variant"],
        variant_path=variant_path,
        patch_path=patch_path,
        sot_path=sot_path,
    )


def _project_metadata(project_dir: Path, data: dict[str, Any]) -> ProjectMetadata:
    created_at = _project_timestamp(data.get("created_at"))
    job = _metadata_mapping(data.get("job"), "job")
    source = _metadata_mapping(job.get("source"), "job.source")
    signals = _metadata_mapping(data.get("signals"), "signals")
    raw = job.get("raw_path")
    return ProjectMetadata(
        created_at=created_at,
        source=ProjectJobSource(
            kind=_source_kind(source.get("type")),
            value=_metadata_text(source.get("value"), "job.source.value"),
        ),
        extracted=ProjectArtifactMetadata(
            path=_project_relative_path(
                project_dir, job.get("extracted_path"), "job.extracted_path"
            ),
            recorded_sha256=_metadata_sha256(job.get("extracted_hash"), "job.extracted_hash"),
        ),
        raw_path=_project_relative_path(project_dir, raw, "job.raw_path")
        if raw is not None
        else None,
        signals=ProjectArtifactMetadata(
            path=_project_relative_path(project_dir, signals.get("path"), "signals.path"),
            recorded_sha256=_metadata_sha256(signals.get("hash"), "signals.hash"),
        ),
    )


def _metadata_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProjectError(f"Project {field} must be a mapping")
    return value


def _metadata_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectError(f"Project {field} must be a nonempty string")
    return value.strip()


def _source_kind(value: Any) -> Literal["file", "url"]:
    kind = _metadata_text(value, "job.source.type")
    if kind == "file":
        return "file"
    if kind == "url":
        return "url"
    raise ProjectError("Project job.source.type must be 'file' or 'url'")


def _metadata_sha256(value: Any, field: str) -> str:
    digest = _metadata_text(value, field)
    if re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
        raise ProjectError(f"Project {field} must be a SHA-256 digest (64 hexadecimal characters)")
    return digest


def _project_timestamp(value: Any) -> str:
    message = "Project created_at must be an ISO 8601 timestamp with a timezone"
    if not isinstance(value, (str, datetime)):
        raise ProjectError(message)
    text = str(value).strip()
    try:
        timestamp = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ProjectError(message) from exc
    if timestamp.utcoffset() is None:
        raise ProjectError(message)
    return text


def _project_relative_path(project_dir: Path, value: Any, field: str) -> Path:
    candidate = Path(_metadata_text(value, field))
    try:
        root = project_dir.resolve()
        resolved = (root / candidate).resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProjectError(f"Project {field} path could not be resolved") from exc
    if resolved == root or not resolved.is_relative_to(root):
        raise ProjectError(f"Project {field} must name an artifact within the project directory")
    return resolved
