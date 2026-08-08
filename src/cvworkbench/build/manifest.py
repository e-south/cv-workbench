"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/manifest.py

Builds and writes build manifests for auditability.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cvworkbench.inputs.sot import OPTIONAL_FILES, REQUIRED_FILES
from cvworkbench.variants import Variant


@dataclass(frozen=True)
class ManifestMetadata:
    resume_name: str
    resume_hash: str
    sot_hashes: dict[str, str]
    snippet_hashes: dict[str, str]
    variant_hash: str
    git_commit: str | None
    pandoc_version: str | None
    pdf_engine: str | None
    pdf_engine_version: str | None


def collect_manifest_metadata(
    *,
    variant_path: Path,
    sot_path: Path,
    resume_path: Path,
    pdf_engine: str | None,
    repo_root: Path,
) -> ManifestMetadata:
    task_count = 7 if pdf_engine else 6
    with ThreadPoolExecutor(max_workers=task_count) as executor:
        resume_hash_future = executor.submit(_hash_file, resume_path)
        sot_hashes_future = executor.submit(_hash_sot, sot_path)
        snippet_hashes_future = executor.submit(_hash_snippets, sot_path)
        variant_hash_future = executor.submit(_hash_file, variant_path)
        git_commit_future = executor.submit(_git_commit, repo_root)
        pandoc_version_future = executor.submit(_tool_version, ["pandoc", "--version"])
        pdf_engine_version_future = (
            executor.submit(_tool_version, [pdf_engine, "--version"]) if pdf_engine else None
        )

    return ManifestMetadata(
        resume_name=resume_path.name,
        resume_hash=resume_hash_future.result(),
        sot_hashes=sot_hashes_future.result(),
        snippet_hashes=snippet_hashes_future.result(),
        variant_hash=variant_hash_future.result(),
        git_commit=git_commit_future.result(),
        pandoc_version=pandoc_version_future.result(),
        pdf_engine=pdf_engine,
        pdf_engine_version=pdf_engine_version_future.result()
        if pdf_engine_version_future
        else None,
    )


def build_manifest(
    *,
    variant: Variant,
    formats: list[str],
    output_paths: dict[str, Path],
    metadata: ManifestMetadata,
    render: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    payload = {
        "variant": {
            "id": variant.id,
            "document_type": variant.document_type,
            "output_name": variant.output_name,
            "outputs": list(variant.outputs),
            "include_tags": list(variant.include_tags),
            "exclude_tags": list(variant.exclude_tags),
            "contact_fields": list(variant.contact_fields),
            "max_bullets_per_role": variant.max_bullets_per_role,
            "order": list(variant.order),
        },
        "formats": list(formats),
        "outputs": {fmt: output_paths[fmt].name for fmt in formats if fmt in output_paths},
        "output_hashes": {
            fmt: _hash_file(output_paths[fmt]) for fmt in formats if fmt in output_paths
        },
        "resume": {
            "path": metadata.resume_name,
            "hash": metadata.resume_hash,
        },
        "sot_hashes": metadata.sot_hashes,
        "snippet_hashes": metadata.snippet_hashes,
        "variant_hash": metadata.variant_hash,
        "git": {"commit": metadata.git_commit},
        "tools": {
            "pandoc": metadata.pandoc_version,
            "pdf_engine": metadata.pdf_engine,
            "pdf_engine_version": metadata.pdf_engine_version,
        },
    }
    if created_at is not None:
        payload["created_at"] = created_at
    if render is not None:
        payload["render"] = render
    return payload


def write_manifest(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True)
    path.write_text(f"{payload}\n")


def _hash_sot(sot_path: Path) -> dict[str, str]:
    hashes = {filename: _hash_file(sot_path / filename) for filename in REQUIRED_FILES.keys()}
    for filename in OPTIONAL_FILES.keys():
        path = sot_path / filename
        if path.exists():
            hashes[filename] = _hash_file(path)
    return hashes


def _hash_snippets(sot_path: Path) -> dict[str, str]:
    snippets_path = sot_path / "snippets.yaml"
    if not snippets_path.exists():
        return {}
    raw = yaml.safe_load(snippets_path.read_text())
    if raw is None:
        raise ValueError("snippets.yaml is empty")
    if not isinstance(raw, dict):
        raise ValueError("snippets.yaml must be a YAML mapping")
    snippets = raw.get("snippets")
    if not isinstance(snippets, list):
        raise ValueError("snippets.snippets must be a list")

    hashes: dict[str, str] = {}
    for snippet in snippets:
        if not isinstance(snippet, dict):
            continue
        path_value = snippet.get("path")
        if isinstance(path_value, str) and path_value.strip():
            path = sot_path / path_value
            hashes[path_value] = _hash_file(path)
            continue
        text_value = snippet.get("text")
        if isinstance(text_value, str) and text_value.strip():
            snippet_id = snippet.get("id") or "snippet"
            hashes[f"inline:{snippet_id}"] = _hash_text(text_value)
    return hashes


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_text(text: str) -> str:
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()


def _git_commit(repo_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _tool_version(args: list[str]) -> str | None:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    line = (result.stdout or "").splitlines()
    if not line:
        return None
    value = line[0].strip()
    return value or None
