"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects.py

Creates and manages project workspaces for job tailoring.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any

import yaml

from cvworkbench.config import resolve_config_path, resolve_projects_path, resolve_variant_path
from cvworkbench.ingestion.ingest import IngestError, fetch_and_extract
from cvworkbench.ingestion.registry import load_registry_settings
from cvworkbench.ingestion.signals import build_signals
from cvworkbench.ops.patches import PatchError, apply_patch_text
from cvworkbench.ops.variant_lifecycle import VariantLifecycleError, register_variant
from cvworkbench.text import slugify
from cvworkbench.variants import load_variant


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
    patch_format: str
    patch_is_empty: bool
    patch_line_count: int


@dataclass(frozen=True)
class ProjectPatch:
    format: str
    diff: str
    operations: tuple[dict[str, Any], ...]


_PROJECT_PATCH_FORMAT_UNIFIED_DIFF = "unified-diff"
_PROJECT_PATCH_FORMAT_OPS = "project-ops"
_PROJECT_OP_REPLACE_EXPERIENCE_BULLET = "replace-experience-bullet"
_PROJECT_OP_REPLACE_PROJECT_SUMMARY = "replace-project-summary"


def resolve_project_dir(project: str, config_path: Path) -> Path:
    candidate = Path(project)
    if candidate.is_absolute() or candidate.exists():
        return candidate
    return resolve_projects_path(config_path) / project


def create_project_from_url(
    *,
    url: str,
    slug: str | None,
    base_variant_id: str,
    config_path: Path,
    sot_path: Path,
    store_raw: bool,
) -> ProjectPaths:
    if not url.strip():
        raise ProjectError("Job URL is required")
    config_path = resolve_config_path(config_path)
    if not sot_path.exists():
        raise ProjectError(f"SoT path not found: {sot_path}")

    settings = load_registry_settings(config_path)
    try:
        extract = fetch_and_extract(url, settings.user_agent)
    except IngestError as exc:
        raise ProjectError(str(exc)) from exc

    project_id = _slugify(slug or _project_id_from_url(url))
    if not project_id:
        raise ProjectError("Project id could not be derived from URL")

    project_dir = _prepare_project_dir(project_id, config_path)
    job_dir = project_dir / "job"
    job_dir.mkdir(parents=True, exist_ok=True)

    source_path = job_dir / "source.url"
    source_path.write_text(url.strip() + "\n")

    extracted_path = job_dir / "extracted.txt"
    extracted_path.write_text(extract.text.strip() + "\n")

    raw_path = None
    if store_raw:
        if extract.raw_html is None:
            raise ProjectError("Raw HTML was requested but is unavailable")
        raw_path = job_dir / "raw.html"
        raw_path.write_text(extract.raw_html)

    signals_path = job_dir / "signals.json"
    signals = build_signals(
        extract.text,
        {
            "type": "url",
            "value": url,
            "retrieved_at": _now_iso(),
        },
    )
    signals_path.write_text(json.dumps(signals, indent=2, sort_keys=True) + "\n")

    return _write_project_files(
        project_dir=project_dir,
        project_id=project_id,
        base_variant_id=base_variant_id,
        sot_path=sot_path,
        job_source={"type": "url", "value": url},
        extracted_path=extracted_path,
        raw_path=raw_path,
        signals_path=signals_path,
        config_path=config_path,
    )


def create_project_from_file(
    *,
    job_path: Path,
    slug: str | None,
    base_variant_id: str,
    config_path: Path,
    sot_path: Path,
    store_raw: bool,
) -> ProjectPaths:
    if not job_path.exists():
        raise ProjectError(f"Job file not found: {job_path}")
    if store_raw:
        raise ProjectError("Raw HTML storage is only available for URL ingestion")
    config_path = resolve_config_path(config_path)
    if not sot_path.exists():
        raise ProjectError(f"SoT path not found: {sot_path}")

    project_id = _slugify(slug or job_path.stem)
    if not project_id:
        raise ProjectError("Project id could not be derived from job file")

    project_dir = _prepare_project_dir(project_id, config_path)
    job_dir = project_dir / "job"
    job_dir.mkdir(parents=True, exist_ok=True)

    source_path = job_dir / "source.path"
    source_path.write_text(str(job_path) + "\n")

    extracted_path = job_dir / "extracted.txt"
    extracted_path.write_text(job_path.read_text().strip() + "\n")

    signals_path = job_dir / "signals.json"
    signals = build_signals(
        extracted_path.read_text(),
        {
            "type": "file",
            "value": str(job_path),
            "retrieved_at": _now_iso(),
        },
    )
    signals_path.write_text(json.dumps(signals, indent=2, sort_keys=True) + "\n")

    return _write_project_files(
        project_dir=project_dir,
        project_id=project_id,
        base_variant_id=base_variant_id,
        sot_path=sot_path,
        job_source={"type": "file", "value": str(job_path)},
        extracted_path=extracted_path,
        raw_path=None,
        signals_path=signals_path,
        config_path=config_path,
    )


def _write_project_files(
    *,
    project_dir: Path,
    project_id: str,
    base_variant_id: str,
    sot_path: Path,
    job_source: dict[str, Any],
    extracted_path: Path,
    raw_path: Path | None,
    signals_path: Path,
    config_path: Path,
) -> ProjectPaths:
    proposals_dir = project_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)

    variant_source_path = resolve_variant_path(base_variant_id, config_path)
    if not variant_source_path.exists():
        raise ProjectError(f"Base variant not found: {base_variant_id}")
    variant_path = proposals_dir / "variant.yaml"
    proposal_variant_id = suggest_project_variant_id(project_id=project_id, config_path=config_path)
    raw_variant = yaml.safe_load(variant_source_path.read_text())
    if not isinstance(raw_variant, dict):
        raise ProjectError(f"Variant file must be a mapping: {variant_source_path}")
    variant_data = raw_variant.get("variant")
    if not isinstance(variant_data, dict):
        raise ProjectError(f"Variant file is invalid: {variant_source_path}")
    variant_data["id"] = proposal_variant_id
    variant_path.write_text(yaml.safe_dump(raw_variant, sort_keys=False))

    patch_path = proposals_dir / "patch.yaml"
    patch_payload = {
        "created_at": _now_iso(),
        "patch": {
            "format": _PROJECT_PATCH_FORMAT_OPS,
            "operations": [],
        },
    }
    patch_path.write_text(yaml.safe_dump(patch_payload, sort_keys=False))

    project_file = project_dir / "project.yaml"
    project_payload = {
        "project": {
            "id": project_id,
            "created_at": _now_iso(),
            "base_variant": base_variant_id,
            "sot_path": str(sot_path.resolve()),
            "job": {
                "source": job_source,
                "extracted_path": str(_relative_path(project_dir, extracted_path)),
                "extracted_hash": _hash_file(extracted_path),
                "raw_path": str(_relative_path(project_dir, raw_path)) if raw_path else None,
            },
            "signals": {
                "path": str(_relative_path(project_dir, signals_path)),
                "hash": _hash_file(signals_path),
            },
        }
    }
    project_file.write_text(yaml.safe_dump(project_payload, sort_keys=False))

    try:
        register_variant(
            variant_path=variant_path,
            cleanup_path=proposals_dir,
            source="project",
            config_path=config_path,
            label=project_id,
        )
    except VariantLifecycleError as exc:
        raise ProjectError(str(exc)) from exc

    return ProjectPaths(
        project_dir=project_dir,
        project_file=project_file,
        job_dir=project_dir / "job",
        extracted_path=extracted_path,
        signals_path=signals_path,
        raw_path=raw_path,
        variant_path=variant_path,
        patch_path=patch_path,
    )


def load_project(project_dir: Path) -> ProjectSpec:
    if not project_dir.exists():
        raise ProjectError(f"Project directory not found: {project_dir}")
    project_file = project_dir / "project.yaml"
    if not project_file.exists():
        raise ProjectError(f"Project manifest not found: {project_file}")
    raw = yaml.safe_load(project_file.read_text())
    if not isinstance(raw, dict):
        raise ProjectError("Project manifest must be a mapping")
    project_data = raw.get("project")
    if not isinstance(project_data, dict):
        raise ProjectError("Project manifest is invalid")
    project_id = str(project_data.get("id", "")).strip()
    if not project_id:
        raise ProjectError("Project id is required")
    base_variant = str(project_data.get("base_variant", "")).strip()
    if not base_variant:
        raise ProjectError("Project base_variant is required")
    sot_path_value = project_data.get("sot_path")
    if not isinstance(sot_path_value, str) or not sot_path_value.strip():
        raise ProjectError("Project sot_path is required")
    sot_path = Path(sot_path_value)
    variant_path = project_dir / "proposals" / "variant.yaml"
    patch_path = project_dir / "proposals" / "patch.yaml"
    if not variant_path.exists():
        raise ProjectError(f"Project variant not found: {variant_path}")
    if not patch_path.exists():
        raise ProjectError(f"Project patch not found: {patch_path}")
    return ProjectSpec(
        project_id=project_id,
        project_dir=project_dir,
        base_variant_id=base_variant,
        variant_path=variant_path,
        patch_path=patch_path,
        sot_path=sot_path,
    )


def load_project_details(project_dir: Path) -> ProjectDetails:
    spec = load_project(project_dir)
    project_file = project_dir / "project.yaml"
    raw = yaml.safe_load(project_file.read_text())
    project_data = raw.get("project") if isinstance(raw, dict) else None
    if not isinstance(project_data, dict):
        raise ProjectError("Project manifest is invalid")

    created_at = str(project_data.get("created_at", "")).strip()
    if not created_at:
        raise ProjectError("Project created_at is required")

    job_data = project_data.get("job")
    if not isinstance(job_data, dict):
        raise ProjectError("Project job metadata is invalid")
    source_data = job_data.get("source")
    if not isinstance(source_data, dict):
        raise ProjectError("Project job source metadata is invalid")
    job_source_type = str(source_data.get("type", "")).strip()
    job_source_value = str(source_data.get("value", "")).strip()
    if not job_source_type or not job_source_value:
        raise ProjectError("Project job source metadata is incomplete")

    extracted_path = _project_relative_path(project_dir, job_data.get("extracted_path"))
    raw_value = job_data.get("raw_path")
    raw_path = _project_relative_path(project_dir, raw_value) if raw_value else None

    signals_data = project_data.get("signals")
    if not isinstance(signals_data, dict):
        raise ProjectError("Project signals metadata is invalid")
    signals_path = _project_relative_path(project_dir, signals_data.get("path"))
    signals_hash = str(signals_data.get("hash", "")).strip()
    if not signals_hash:
        raise ProjectError("Project signals hash is required")

    try:
        proposal_variant_id = load_variant(spec.variant_path).id
    except ValueError as exc:
        raise ProjectError(str(exc)) from exc

    patch = _load_project_patch_model(project_dir)
    if patch.format == _PROJECT_PATCH_FORMAT_UNIFIED_DIFF:
        patch_is_empty = patch.diff.strip() == ""
        patch_line_count = len(patch.diff.splitlines())
    else:
        patch_is_empty = len(patch.operations) == 0
        patch_line_count = len(patch.operations)

    return ProjectDetails(
        spec=spec,
        created_at=created_at,
        job_source_type=job_source_type,
        job_source_value=job_source_value,
        extracted_path=extracted_path,
        raw_path=raw_path,
        signals_path=signals_path,
        signals_hash=signals_hash,
        proposal_variant_id=proposal_variant_id,
        patch_format=patch.format,
        patch_is_empty=patch_is_empty,
        patch_line_count=patch_line_count,
    )


def load_project_patch(project_dir: Path, *, sot_path: Path | None = None) -> str:
    patch = _load_project_patch_model(project_dir)
    return compile_project_patch(patch=patch, sot_path=sot_path)


def suggest_project_variant_id(
    *,
    project_id: str,
    config_path: Path,
    preferred_id: str | None = None,
) -> str:
    candidate = (preferred_id or "").strip()
    if candidate and candidate != "base" and not resolve_variant_path(candidate, config_path).exists():
        return candidate
    base = _slugify(f"proposal-{project_id}") or "proposal"
    for suffix in range(0, 1000):
        candidate = base if suffix == 0 else f"{base}-{suffix:02d}"
        if not resolve_variant_path(candidate, config_path).exists():
            return candidate
    raise ProjectError(f"Could not allocate project proposal variant id for: {project_id}")


def _load_project_patch_model(project_dir: Path) -> ProjectPatch:
    patch_path = project_dir / "proposals" / "patch.yaml"
    return load_project_patch_payload(patch_path)


def load_project_patch_payload(patch_path: Path) -> ProjectPatch:
    if not patch_path.exists():
        raise ProjectError(f"Project patch not found: {patch_path}")
    raw = yaml.safe_load(patch_path.read_text())
    if not isinstance(raw, dict):
        raise ProjectError("Project patch file must be a mapping")
    patch_data = raw.get("patch")
    if not isinstance(patch_data, dict):
        raise ProjectError("Project patch file is invalid")
    fmt = patch_data.get("format")
    if fmt == _PROJECT_PATCH_FORMAT_UNIFIED_DIFF:
        diff = patch_data.get("diff")
        if not isinstance(diff, str):
            raise ProjectError("Project patch diff must be a string")
        return ProjectPatch(format=fmt, diff=diff, operations=())
    if fmt == _PROJECT_PATCH_FORMAT_OPS:
        operations = patch_data.get("operations")
        if not isinstance(operations, list):
            raise ProjectError("Project patch operations must be a list")
        if not all(isinstance(item, dict) for item in operations):
            raise ProjectError("Project patch operations must be mappings")
        return ProjectPatch(
            format=fmt,
            diff="",
            operations=tuple(dict(item) for item in operations),
        )
    raise ProjectError("Project patch format must be unified-diff or project-ops")


def compile_project_patch(*, patch: ProjectPatch, sot_path: Path | None = None) -> str:
    if patch.format == _PROJECT_PATCH_FORMAT_UNIFIED_DIFF:
        return patch.diff
    if len(patch.operations) == 0:
        return ""
    if sot_path is None:
        raise ProjectError("SoT path is required to compile project patch operations")
    return _compile_project_operations(operations=patch.operations, sot_path=sot_path)


def apply_project_patch(*, project_dir: Path, sot_path: Path) -> None:
    diff = load_project_patch(project_dir, sot_path=sot_path)
    try:
        apply_patch_text(patch_text=diff, cwd=sot_path)
    except PatchError as exc:
        raise ProjectError(str(exc)) from exc


def prepare_project_sot(*, project_dir: Path, sot_path: Path, target_dir: Path) -> Path:
    diff = load_project_patch(project_dir, sot_path=sot_path)
    if diff.strip() == "":
        return sot_path
    if target_dir.exists():
        import shutil

        shutil.rmtree(target_dir)
    import shutil

    shutil.copytree(sot_path, target_dir)
    try:
        apply_patch_text(patch_text=diff, cwd=target_dir)
    except PatchError as exc:
        raise ProjectError(str(exc)) from exc
    return target_dir


def append_replace_experience_bullet_operation(
    *,
    project_dir: Path,
    sot_path: Path,
    role_id: str,
    bullet_id: str,
    new_text: str,
    old_text: str | None = None,
) -> ProjectPatch:
    resolved_role_id = _require_project_text(role_id, field_name="role_id", slug=True)
    resolved_bullet_id = _require_project_text(bullet_id, field_name="bullet_id", slug=True)
    resolved_new_text = _require_project_text(new_text, field_name="new_text")
    current_text = _read_experience_bullet_text(
        sot_path=sot_path,
        role_id=resolved_role_id,
        bullet_id=resolved_bullet_id,
    )
    resolved_old_text = (
        current_text
        if old_text is None
        else _require_project_text(old_text, field_name="old_text")
    )
    if resolved_old_text == resolved_new_text:
        raise ProjectError("Project op replacement text must differ from source text")

    return _append_project_operation(
        project_dir=project_dir,
        sot_path=sot_path,
        operation=_experience_bullet_operation(
            role_id=resolved_role_id,
            bullet_id=resolved_bullet_id,
            old_text=resolved_old_text,
            new_text=resolved_new_text,
        ),
    )


def append_replace_project_summary_operation(
    *,
    project_dir: Path,
    sot_path: Path,
    project_id: str,
    new_text: str,
    old_text: str | None = None,
) -> ProjectPatch:
    resolved_project_id = _require_project_text(project_id, field_name="project_id", slug=True)
    resolved_new_text = _require_project_text(new_text, field_name="new_text")
    current_text = _read_project_summary_text(
        sot_path=sot_path,
        project_id=resolved_project_id,
    )
    resolved_old_text = (
        current_text
        if old_text is None
        else _require_project_text(old_text, field_name="old_text")
    )
    if resolved_old_text == resolved_new_text:
        raise ProjectError("Project op replacement text must differ from source text")

    return _append_project_operation(
        project_dir=project_dir,
        sot_path=sot_path,
        operation=_project_summary_operation(
            project_id=resolved_project_id,
            old_text=resolved_old_text,
            new_text=resolved_new_text,
        ),
    )


def _compile_project_operations(
    *,
    operations: tuple[dict[str, Any], ...],
    sot_path: Path,
) -> str:
    experience: tuple[str, dict[str, Any], list[Any]] | None = None
    projects: tuple[str, dict[str, Any], list[Any]] | None = None
    bullet_index: dict[tuple[str, str], dict[str, Any]] | None = None
    duplicate_bullets: set[tuple[str, str]] = set()
    seen_bullet_targets: set[tuple[str, str]] = set()
    project_index: dict[str, dict[str, Any]] | None = None
    duplicate_projects: set[str] = set()
    seen_project_targets: set[str] = set()

    for index, operation in enumerate(operations, start=1):
        op_name = _require_operation_text(operation, "op", index=index)
        if op_name == _PROJECT_OP_REPLACE_EXPERIENCE_BULLET:
            if experience is None:
                experience = _load_project_ops_document(
                    sot_path=sot_path,
                    filename="experience.yaml",
                    root_key="roles",
                )
                bullet_index, duplicate_bullets = _index_experience_bullets(experience[2])
            assert bullet_index is not None
            role_id = _require_operation_slug(operation, "role_id", index=index)
            bullet_id = _require_operation_slug(operation, "bullet_id", index=index)
            old_text = _require_operation_text(operation, "old_text", index=index)
            new_text = _require_operation_text(operation, "new_text", index=index)
            target = (role_id, bullet_id)
            if target in seen_bullet_targets:
                raise ProjectError(
                    "Duplicate project op target for experience bullet: "
                    f"role_id={role_id} bullet_id={bullet_id}"
                )
            seen_bullet_targets.add(target)
            if target in duplicate_bullets:
                raise ProjectError(
                    "Project op target resolves to a duplicate experience bullet target: "
                    f"role_id={role_id} bullet_id={bullet_id}"
                )
            bullet = bullet_index.get(target)
            if bullet is None:
                raise ProjectError(
                    "Project op target not found in experience.yaml: "
                    f"role_id={role_id} bullet_id={bullet_id}"
                )
            current_text = bullet.get("text")
            if not isinstance(current_text, str) or not current_text.strip():
                raise ProjectError(
                    "Experience bullet text is invalid for project op target: "
                    f"role_id={role_id} bullet_id={bullet_id}"
                )
            if current_text != old_text:
                raise ProjectError(
                    "Project op source text mismatch for experience bullet: "
                    f"role_id={role_id} bullet_id={bullet_id}"
                )
            bullet["text"] = new_text
            continue

        if op_name == _PROJECT_OP_REPLACE_PROJECT_SUMMARY:
            if projects is None:
                projects = _load_project_ops_document(
                    sot_path=sot_path,
                    filename="projects.yaml",
                    root_key="projects",
                )
                project_index, duplicate_projects = _index_projects(projects[2])
            assert project_index is not None
            project_id = _require_operation_slug(operation, "project_id", index=index)
            old_text = _require_operation_text(operation, "old_text", index=index)
            new_text = _require_operation_text(operation, "new_text", index=index)
            if project_id in seen_project_targets:
                raise ProjectError(
                    "Duplicate project op target for project summary: "
                    f"project_id={project_id}"
                )
            seen_project_targets.add(project_id)
            if project_id in duplicate_projects:
                raise ProjectError(
                    "Project op target resolves to a duplicate project summary target: "
                    f"project_id={project_id}"
                )
            project_entry = project_index.get(project_id)
            if project_entry is None:
                raise ProjectError(
                    "Project op target not found in projects.yaml: "
                    f"project_id={project_id}"
                )
            current_summary = project_entry.get("summary")
            if not isinstance(current_summary, str) or not current_summary.strip():
                raise ProjectError(
                    "Project summary text is invalid for project op target: "
                    f"project_id={project_id}"
                )
            if current_summary != old_text:
                raise ProjectError(
                    "Project op source text mismatch for project summary: "
                    f"project_id={project_id}"
                )
            project_entry["summary"] = new_text
            continue

        raise ProjectError(f"Unsupported project operation: {op_name}")

    diffs: list[str] = []
    if experience is not None:
        diffs.append(
            _project_ops_diff(
                filename="experience.yaml",
                original_text=experience[0],
                updated_text=yaml.safe_dump(experience[1], sort_keys=False),
            )
        )
    if projects is not None:
        diffs.append(
            _project_ops_diff(
                filename="projects.yaml",
                original_text=projects[0],
                updated_text=yaml.safe_dump(projects[1], sort_keys=False),
            )
        )
    return "".join(diff for diff in diffs if diff)


def _index_experience_bullets(
    roles: list[Any],
) -> tuple[dict[tuple[str, str], dict[str, Any]], set[tuple[str, str]]]:
    bullets: dict[tuple[str, str], dict[str, Any]] = {}
    duplicates: set[tuple[str, str]] = set()
    for role in roles:
        if not isinstance(role, dict):
            continue
        role_id = slugify(role.get("id", ""))
        if not role_id:
            continue
        raw_bullets = role.get("bullets")
        if not isinstance(raw_bullets, list):
            continue
        for bullet in raw_bullets:
            if not isinstance(bullet, dict):
                continue
            bullet_id = slugify(bullet.get("id", ""))
            if not bullet_id:
                continue
            target = (role_id, bullet_id)
            if target in bullets:
                duplicates.add(target)
                continue
            bullets[target] = bullet
    return bullets, duplicates


def _experience_bullet_operation(
    *,
    role_id: str,
    bullet_id: str,
    old_text: str,
    new_text: str,
) -> dict[str, str]:
    return {
        "op": _PROJECT_OP_REPLACE_EXPERIENCE_BULLET,
        "role_id": role_id,
        "bullet_id": bullet_id,
        "old_text": old_text,
        "new_text": new_text,
    }


def _project_summary_operation(
    *,
    project_id: str,
    old_text: str,
    new_text: str,
) -> dict[str, str]:
    return {
        "op": _PROJECT_OP_REPLACE_PROJECT_SUMMARY,
        "project_id": project_id,
        "old_text": old_text,
        "new_text": new_text,
    }


def _read_experience_bullet_text(
    *,
    sot_path: Path,
    role_id: str,
    bullet_id: str,
) -> str:
    _, _, roles = _load_project_ops_document(
        sot_path=sot_path,
        filename="experience.yaml",
        root_key="roles",
    )
    bullet_index, duplicate_targets = _index_experience_bullets(roles)
    target = (role_id, bullet_id)
    if target in duplicate_targets:
        raise ProjectError(
            "Project op target resolves to a duplicate experience bullet target: "
            f"role_id={role_id} bullet_id={bullet_id}"
        )
    bullet = bullet_index.get(target)
    if bullet is None:
        raise ProjectError(
            "Project op target not found in experience.yaml: "
            f"role_id={role_id} bullet_id={bullet_id}"
        )
    current_text = bullet.get("text")
    if not isinstance(current_text, str) or not current_text.strip():
        raise ProjectError(
            "Experience bullet text is invalid for project op target: "
            f"role_id={role_id} bullet_id={bullet_id}"
        )
    return current_text.strip()


def _read_project_summary_text(
    *,
    sot_path: Path,
    project_id: str,
) -> str:
    _, _, items = _load_project_ops_document(
        sot_path=sot_path,
        filename="projects.yaml",
        root_key="projects",
    )
    project_index, duplicate_targets = _index_projects(items)
    if project_id in duplicate_targets:
        raise ProjectError(
            "Project op target resolves to a duplicate project summary target: "
            f"project_id={project_id}"
        )
    project_entry = project_index.get(project_id)
    if project_entry is None:
        raise ProjectError(
            "Project op target not found in projects.yaml: "
            f"project_id={project_id}"
        )
    current_summary = project_entry.get("summary")
    if not isinstance(current_summary, str) or not current_summary.strip():
        raise ProjectError(
            "Project summary text is invalid for project op target: "
            f"project_id={project_id}"
        )
    return current_summary.strip()


def _load_project_ops_document(
    *,
    sot_path: Path,
    filename: str,
    root_key: str,
) -> tuple[str, dict[str, Any], list[Any]]:
    target_path = sot_path / filename
    if not target_path.exists():
        raise ProjectError(f"Project ops target file not found: {target_path}")
    original_text = target_path.read_text()
    raw = yaml.safe_load(original_text)
    if not isinstance(raw, dict):
        raise ProjectError(f"{filename} must be a mapping")
    items = raw.get(root_key)
    if not isinstance(items, list):
        raise ProjectError(f"{filename} must contain a {root_key} list")
    return original_text, raw, items


def _append_project_operation(
    *,
    project_dir: Path,
    sot_path: Path,
    operation: dict[str, str],
) -> ProjectPatch:
    patch_path, raw, patch_data, operations = _load_project_patch_authoring_state(project_dir)
    candidate_operations = tuple([*operations, operation])
    _compile_project_operations(operations=candidate_operations, sot_path=sot_path)

    patch_data["operations"] = list(candidate_operations)
    raw.setdefault("created_at", _now_iso())
    raw["updated_at"] = _now_iso()
    patch_path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return ProjectPatch(
        format=_PROJECT_PATCH_FORMAT_OPS,
        diff="",
        operations=candidate_operations,
    )


def _load_project_patch_authoring_state(
    project_dir: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    patch_path = project_dir / "proposals" / "patch.yaml"
    raw = yaml.safe_load(patch_path.read_text())
    if not isinstance(raw, dict):
        raise ProjectError("Project patch file must be a mapping")
    patch_data = raw.get("patch")
    if not isinstance(patch_data, dict):
        raise ProjectError("Project patch file is invalid")
    if patch_data.get("format") != _PROJECT_PATCH_FORMAT_OPS:
        raise ProjectError(
            "Project patch authoring requires format=project-ops in proposals/patch.yaml"
        )
    operations = patch_data.get("operations")
    if not isinstance(operations, list):
        raise ProjectError("Project patch operations must be a list")
    if not all(isinstance(item, dict) for item in operations):
        raise ProjectError("Project patch operations must be mappings")
    return patch_path, raw, patch_data, [dict(item) for item in operations]


def _index_projects(items: list[Any]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    projects: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        project_id = slugify(item.get("id", ""))
        if not project_id:
            continue
        if project_id in projects:
            duplicates.add(project_id)
            continue
        projects[project_id] = item
    return projects, duplicates


def _project_ops_diff(*, filename: str, original_text: str, updated_text: str) -> str:
    diff = unified_diff(
        original_text.splitlines(),
        updated_text.splitlines(),
        fromfile=filename,
        tofile=filename,
        lineterm="",
    )
    return "\n".join(diff) + ("\n" if original_text or updated_text else "")


def _require_project_text(value: str, *, field_name: str, slug: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectError(f"Project op field '{field_name}' must be a non-empty string")
    normalized = value.strip()
    if not slug:
        return normalized
    resolved = slugify(normalized)
    if not resolved:
        raise ProjectError(f"Project op field '{field_name}' must resolve to a stable id")
    return resolved


def _require_operation_text(
    operation: dict[str, Any],
    key: str,
    *,
    index: int,
) -> str:
    value = operation.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProjectError(f"Project op #{index} field '{key}' must be a non-empty string")
    return value.strip()


def _require_operation_slug(
    operation: dict[str, Any],
    key: str,
    *,
    index: int,
) -> str:
    value = _require_operation_text(operation, key, index=index)
    normalized = slugify(value)
    if not normalized:
        raise ProjectError(f"Project op #{index} field '{key}' must resolve to a stable id")
    return normalized


def _prepare_project_dir(project_id: str, config_path: Path) -> Path:
    projects_root = resolve_projects_path(config_path)
    project_dir = projects_root / project_id
    if project_dir.exists():
        raise ProjectError(f"Project already exists: {project_dir}")
    project_dir.mkdir(parents=True, exist_ok=False)
    return project_dir


def _relative_path(root: Path, target: Path | None) -> Path | None:
    if target is None:
        return None
    try:
        return target.relative_to(root)
    except ValueError:
        return target


def _project_relative_path(project_dir: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ProjectError("Project manifest path metadata is incomplete")
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (project_dir / candidate)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _project_id_from_url(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return f"project-{digest[:8]}"


def _slugify(value: str) -> str:
    cleaned: list[str] = []
    for char in value.lower():
        if char.isalnum():
            cleaned.append(char)
        else:
            cleaned.append("-")
    slug = "".join(cleaned)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
