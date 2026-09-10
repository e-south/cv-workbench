"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/creation.py

Create, retarget, register, and discard private project workspaces.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from cvworkbench.config import (
    ConfigSource,
    read_config,
    resolve_projects_path,
    resolve_variant_path,
)
from cvworkbench.ingestion.ingest import IngestError, fetch_and_extract
from cvworkbench.ingestion.registry import load_registry_settings
from cvworkbench.ingestion.signals import build_signals
from cvworkbench.ops.atomic import AtomicWriteError, replace_files_atomically
from cvworkbench.ops.projects.identity import (
    _project_id_from_url,
    _slugify,
    suggest_project_variant_id,
)
from cvworkbench.ops.projects.manifest import load_project
from cvworkbench.ops.projects.records import (
    _PROJECT_PATCH_FORMAT_OPS,
    ProjectError,
    ProjectPaths,
    ProjectSpec,
    _now_iso,
)
from cvworkbench.ops.variant_lifecycle import (
    VariantLifecycleError,
    discard_variant,
    register_variant,
)
from cvworkbench.variants import load_variant


def create_project_from_url(
    *,
    url: str,
    slug: str | None,
    base_variant_id: str,
    config_path: ConfigSource,
    sot_path: Path,
    store_raw: bool,
) -> ProjectPaths:
    if not url.strip():
        raise ProjectError("Job URL is required")
    config_path = read_config(config_path)
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

    with _project_creation(project_id, config_path) as (final_dir, staging_dir):
        job_dir = staging_dir / "job"
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

        _write_project_files(
            project_dir=staging_dir,
            project_id=project_id,
            base_variant_id=base_variant_id,
            sot_path=sot_path,
            job_source={"type": "url", "value": url},
            extracted_path=extracted_path,
            raw_path=raw_path,
            signals_path=signals_path,
            config_path=config_path,
        )
    return _project_paths(final_dir)


def create_project_from_file(
    *,
    job_path: Path,
    slug: str | None,
    base_variant_id: str,
    config_path: ConfigSource,
    sot_path: Path,
    store_raw: bool,
) -> ProjectPaths:
    if not job_path.exists():
        raise ProjectError(f"Job file not found: {job_path}")
    if store_raw:
        raise ProjectError("Raw HTML storage is only available for URL ingestion")
    config_path = read_config(config_path)
    if not sot_path.exists():
        raise ProjectError(f"SoT path not found: {sot_path}")

    project_id = _slugify(slug or job_path.stem)
    if not project_id:
        raise ProjectError("Project id could not be derived from job file")

    with _project_creation(project_id, config_path) as (final_dir, staging_dir):
        job_dir = staging_dir / "job"
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

        _write_project_files(
            project_dir=staging_dir,
            project_id=project_id,
            base_variant_id=base_variant_id,
            sot_path=sot_path,
            job_source={"type": "file", "value": str(job_path)},
            extracted_path=extracted_path,
            raw_path=None,
            signals_path=signals_path,
            config_path=config_path,
        )
    return _project_paths(final_dir)


def retarget_project_variant(
    *,
    project_dir: Path,
    base_variant_id: str,
    config_path: ConfigSource,
) -> ProjectSpec:
    spec = load_project(project_dir)
    project_file = project_dir / "project.yaml"
    raw_project = yaml.safe_load(project_file.read_text())
    if not isinstance(raw_project, dict):
        raise ProjectError("Project manifest must be a mapping")
    project_data = raw_project.get("project")
    if not isinstance(project_data, dict):
        raise ProjectError("Project manifest is invalid")

    proposal_variant_id = load_variant(spec.variant_path).id
    variant_payload = _build_project_variant_payload(
        base_variant_id=base_variant_id,
        proposal_variant_id=proposal_variant_id,
        config_path=config_path,
    )
    project_data["base_variant"] = base_variant_id
    try:
        replace_files_atomically(
            [
                (
                    spec.variant_path,
                    yaml.safe_dump(variant_payload, sort_keys=False).encode("utf-8"),
                ),
                (project_file, yaml.safe_dump(raw_project, sort_keys=False).encode("utf-8")),
            ]
        )
    except AtomicWriteError as exc:
        raise ProjectError(f"Project retarget failed: {exc}") from exc
    return load_project(project_dir)


def discard_project_workspace(*, project_dir: Path, config_path: ConfigSource) -> None:
    errors: list[str] = []
    try:
        spec = load_project(project_dir)
    except ProjectError as exc:
        spec = None
        errors.append(str(exc))
    if spec is not None:
        try:
            discard_variant(
                variant_path=spec.variant_path,
                config_path=config_path,
                confirm=True,
            )
        except VariantLifecycleError as exc:
            errors.append(str(exc))
    if project_dir.exists():
        try:
            shutil.rmtree(project_dir)
        except OSError as exc:
            errors.append(f"Failed to remove project workspace: {exc}")
    if errors:
        raise ProjectError("; ".join(errors))


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
    config_path: ConfigSource,
) -> None:
    proposals_dir = project_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)

    variant_path = proposals_dir / "variant.yaml"
    proposal_variant_id = suggest_project_variant_id(project_id=project_id, config_path=config_path)
    variant_payload = _build_project_variant_payload(
        base_variant_id=base_variant_id,
        proposal_variant_id=proposal_variant_id,
        config_path=config_path,
    )
    variant_path.write_text(yaml.safe_dump(variant_payload, sort_keys=False))

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

    return None


def _build_project_variant_payload(
    *,
    base_variant_id: str,
    proposal_variant_id: str,
    config_path: ConfigSource,
) -> dict[str, Any]:
    variant_source_path = resolve_variant_path(base_variant_id, config_path)
    if not variant_source_path.exists():
        raise ProjectError(f"Base variant not found: {base_variant_id}")
    raw_variant = yaml.safe_load(variant_source_path.read_text())
    if not isinstance(raw_variant, dict):
        raise ProjectError(f"Variant file must be a mapping: {variant_source_path}")
    variant_data = raw_variant.get("variant")
    if not isinstance(variant_data, dict):
        raise ProjectError(f"Variant file is invalid: {variant_source_path}")
    variant_data["id"] = proposal_variant_id
    return raw_variant


@contextmanager
def _project_creation(project_id: str, config_path: ConfigSource) -> Iterator[tuple[Path, Path]]:
    final_dir, staging_dir = _prepare_project_dir(project_id, config_path)
    identity = _directory_identity(staging_dir)
    published = False
    try:
        yield final_dir, staging_dir
        staging_dir.rename(final_dir)
        published = True
        _register_project_variant(final_dir=final_dir, config_path=config_path, label=project_id)
    except BaseException as exc:
        owned_dir = final_dir if published else staging_dir
        try:
            _cleanup_project_dir(owned_dir, identity)
        except (OSError, ProjectError) as cleanup_exc:
            detail = f"Project creation cleanup failed at {owned_dir}: {cleanup_exc}"
            if isinstance(exc, Exception):
                raise ProjectError(f"{exc}; {detail}") from exc
            exc.add_note(detail)
        raise


def _prepare_project_dir(project_id: str, config_path: ConfigSource) -> tuple[Path, Path]:
    projects_root = resolve_projects_path(config_path)
    projects_root.mkdir(parents=True, exist_ok=True)
    project_dir = projects_root / project_id
    if project_dir.exists():
        raise ProjectError(f"Project already exists: {project_dir}")
    staging_dir = projects_root / f".{project_id}.tmp-{uuid4().hex[:8]}"
    if staging_dir.exists():
        raise ProjectError(f"Project staging directory already exists: {staging_dir}")
    staging_dir.mkdir(parents=True, exist_ok=False)
    return project_dir, staging_dir


def _project_paths(project_dir: Path) -> ProjectPaths:
    raw_path = project_dir / "job" / "raw.html"
    return ProjectPaths(
        project_dir=project_dir,
        project_file=project_dir / "project.yaml",
        job_dir=project_dir / "job",
        extracted_path=project_dir / "job" / "extracted.txt",
        signals_path=project_dir / "job" / "signals.json",
        raw_path=raw_path if raw_path.exists() else None,
        variant_path=project_dir / "proposals" / "variant.yaml",
        patch_path=project_dir / "proposals" / "patch.yaml",
    )


def _register_project_variant(*, final_dir: Path, config_path: ConfigSource, label: str) -> None:
    try:
        register_variant(
            variant_path=final_dir / "proposals" / "variant.yaml",
            cleanup_path=final_dir / "proposals",
            source="project",
            config_path=config_path,
            label=label,
        )
    except VariantLifecycleError as exc:
        raise ProjectError(str(exc)) from exc


def _directory_identity(project_dir: Path) -> tuple[int, int]:
    metadata = project_dir.lstat()
    return metadata.st_dev, metadata.st_ino


def _cleanup_project_dir(project_dir: Path, expected_identity: tuple[int, int]) -> None:
    try:
        observed = _directory_identity(project_dir)
    except FileNotFoundError:
        return
    if observed != expected_identity:
        raise ProjectError(f"Project directory was replaced; left intact: {project_dir}")
    shutil.rmtree(project_dir)


def _relative_path(root: Path, target: Path | None) -> Path | None:
    if target is None:
        return None
    try:
        return target.relative_to(root)
    except ValueError:
        return target


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()
