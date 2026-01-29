"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/manifest.py

Builds and writes build manifests for auditability.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cvworkbench.sot import REQUIRED_FILES
from cvworkbench.variants import Variant


def build_manifest(
    *,
    variant: Variant,
    variant_path: Path,
    sot_path: Path,
    formats: list[str],
    output_paths: dict[str, Path],
    pdf_engine: str | None,
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "variant": {
            "id": variant.id,
            "document_type": variant.document_type,
            "output_name": variant.output_name,
            "outputs": list(variant.outputs),
            "include_tags": list(variant.include_tags),
            "exclude_tags": list(variant.exclude_tags),
            "max_bullets_per_role": variant.max_bullets_per_role,
            "order": list(variant.order),
        },
        "formats": list(formats),
        "outputs": {
            fmt: output_paths[fmt].name
            for fmt in formats
            if fmt in output_paths
        },
        "sot_hashes": _hash_sot(sot_path),
        "variant_hash": _hash_file(variant_path),
        "git": {"commit": _git_commit(repo_root)},
        "tools": {
            "pandoc": _tool_version(["pandoc", "--version"]),
            "pdf_engine": pdf_engine,
            "pdf_engine_version": _tool_version([pdf_engine, "--version"]) if pdf_engine else None,
        },
    }


def write_manifest(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True)
    path.write_text(f"{payload}\n")


def _hash_sot(sot_path: Path) -> dict[str, str]:
    return {filename: _hash_file(sot_path / filename) for filename in REQUIRED_FILES}


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
