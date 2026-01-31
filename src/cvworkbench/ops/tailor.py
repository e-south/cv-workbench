"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/tailor.py

Generates draft variants and patch scaffolding for tailoring.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from cvworkbench.config import resolve_variant_path
from cvworkbench.ops.variant_lifecycle import VariantLifecycleError, register_variant


class TailorError(RuntimeError):
    pass


@dataclass(frozen=True)
class DraftPaths:
    job_path: Path
    variant_path: Path
    patch_path: Path
    prompt_path: Path


def tailor_job(
    *,
    job_path: Path,
    base_variant_id: str,
    output_dir: Path,
    config_path: Path,
) -> DraftPaths:
    if not job_path.exists():
        raise TailorError(f"Job file not found: {job_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    draft_variant_id = _slugify(output_dir.name)
    if not draft_variant_id:
        raise TailorError("Draft variant id could not be derived from output directory")

    base_variant_path = resolve_variant_path(base_variant_id, config_path)
    if not base_variant_path.exists():
        raise TailorError(f"Base variant not found: {base_variant_id}")

    raw_variant = yaml.safe_load(base_variant_path.read_text())
    if not isinstance(raw_variant, dict) or "variant" not in raw_variant:
        raise TailorError("Base variant is invalid")

    variant_section = raw_variant.get("variant", {})
    if not isinstance(variant_section, dict):
        raise TailorError("Base variant is invalid")
    variant_section["id"] = draft_variant_id

    variant_path = output_dir / "variant.yaml"
    variant_path.write_text(yaml.safe_dump(raw_variant, sort_keys=False))

    job_copy_path = output_dir / "job.md"
    job_copy_path.write_text(job_path.read_text())

    patch_path = output_dir / "patch.diff"
    patch_path.write_text("")

    signals_path = output_dir / "signals.json"
    signals_payload = _build_signals(job_path)
    signals_path.write_text(json.dumps(signals_payload, indent=2, sort_keys=True) + "\n")

    prompt_path = output_dir / "prompt.json"
    prompt_payload = _build_prompt_payload(
        job_path=job_path,
        base_variant_id=base_variant_id,
        draft_variant_id=draft_variant_id,
        signals_path=signals_path,
    )
    prompt_path.write_text(json.dumps(prompt_payload, indent=2, sort_keys=True) + "\n")

    try:
        register_variant(
            variant_path=variant_path,
            cleanup_path=output_dir,
            source="draft",
            config_path=config_path,
            label=draft_variant_id,
        )
    except VariantLifecycleError as exc:
        raise TailorError(str(exc)) from exc

    return DraftPaths(
        job_path=job_copy_path,
        variant_path=variant_path,
        patch_path=patch_path,
        prompt_path=prompt_path,
    )


def _build_prompt_payload(
    *,
    job_path: Path,
    base_variant_id: str,
    draft_variant_id: str,
    signals_path: Path,
) -> dict[str, Any]:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "job": {
            "path": str(job_path),
            "hash": _hash_file(job_path),
        },
        "signals": {
            "path": str(signals_path),
            "hash": _hash_file(signals_path),
        },
        "base_variant": base_variant_id,
        "draft_variant": draft_variant_id,
        "instructions": "Generate a tailored variant and patch proposal.",
        "model_id": None,
        "temperature": None,
        "diff_summary": None,
    }


def _build_signals(job_path: Path) -> dict[str, Any]:
    text = job_path.read_text()
    tokens = re.findall(r"[A-Za-z0-9]+", text.lower())
    keywords = _dedupe([token for token in tokens if len(token) >= 3])
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": str(job_path),
            "hash": _hash_file(job_path),
        },
        "keywords": keywords[:25],
        "word_count": len(tokens),
    }


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
