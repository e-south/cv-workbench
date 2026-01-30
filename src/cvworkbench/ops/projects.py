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
from pathlib import Path
from typing import Any

import yaml

from cvworkbench.config import resolve_config_path, resolve_projects_path, resolve_variant_path
from cvworkbench.ingestion.ingest import IngestError, fetch_and_extract
from cvworkbench.ingestion.registry import load_registry_settings
from cvworkbench.ingestion.signals import build_signals
from cvworkbench.ops.patches import PatchError, apply_patch_text


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
    variant_path.write_text(variant_source_path.read_text())

    patch_path = proposals_dir / "patch.yaml"
    patch_payload = {
        "created_at": _now_iso(),
        "patch": {
            "format": "unified-diff",
            "diff": "",
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


def load_project_patch(project_dir: Path) -> str:
    patch_path = project_dir / "proposals" / "patch.yaml"
    if not patch_path.exists():
        raise ProjectError(f"Project patch not found: {patch_path}")
    raw = yaml.safe_load(patch_path.read_text())
    if not isinstance(raw, dict):
        raise ProjectError("Project patch file must be a mapping")
    patch_data = raw.get("patch")
    if not isinstance(patch_data, dict):
        raise ProjectError("Project patch file is invalid")
    fmt = patch_data.get("format")
    diff = patch_data.get("diff")
    if fmt != "unified-diff":
        raise ProjectError("Project patch format must be unified-diff")
    if not isinstance(diff, str):
        raise ProjectError("Project patch diff must be a string")
    return diff


def apply_project_patch(*, project_dir: Path, sot_path: Path) -> None:
    diff = load_project_patch(project_dir)
    try:
        apply_patch_text(patch_text=diff, cwd=sot_path)
    except PatchError as exc:
        raise ProjectError(str(exc)) from exc


def prepare_project_sot(*, project_dir: Path, sot_path: Path, run_dir: Path) -> Path:
    diff = load_project_patch(project_dir)
    if diff.strip() == "":
        return sot_path
    target_dir = run_dir / "sot"
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
