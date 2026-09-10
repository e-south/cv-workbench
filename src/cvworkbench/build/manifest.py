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
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    sot_hashes: Mapping[str, str],
    snippet_hashes: Mapping[str, str],
    variant_hash: str,
    resume_name: str,
    resume_content: bytes,
    pdf_engine: str | None,
    repo_root: Path,
) -> ManifestMetadata:
    task_count = 3 if pdf_engine else 2
    with ThreadPoolExecutor(max_workers=task_count) as executor:
        git_commit_future = executor.submit(_git_commit, repo_root)
        pandoc_version_future = executor.submit(_tool_version, ["pandoc", "--version"])
        pdf_engine_version_future = (
            executor.submit(_tool_version, [pdf_engine, "--version"]) if pdf_engine else None
        )

    return ManifestMetadata(
        resume_name=resume_name,
        resume_hash=hashlib.sha256(resume_content).hexdigest(),
        sot_hashes=dict(sot_hashes),
        snippet_hashes=dict(snippet_hashes),
        variant_hash=variant_hash,
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
    configuration_sha256: str,
    render: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    payload = {
        "configuration": {"sha256": configuration_sha256},
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
            "section_titles": dict(variant.section_titles),
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


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
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
