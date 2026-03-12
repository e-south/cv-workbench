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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from cvworkbench.config import resolve_variant_path
from cvworkbench.ingestion.signals import build_signals as build_job_signals
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
        signals_payload=signals_payload,
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
    signals_payload: dict[str, Any],
) -> dict[str, Any]:
    keywords = signals_payload.get("keywords")
    evidence = signals_payload.get("evidence")
    evidence_items = [
        {"keyword": key, "mentions": len(value)}
        for key, value in (evidence.items() if isinstance(evidence, dict) else [])
        if isinstance(key, str) and isinstance(value, list)
    ]
    evidence_items.sort(key=lambda item: (-item["mentions"], item["keyword"]))
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "job": {
            "path": str(job_path),
            "hash": _hash_file(job_path),
            "keywords": keywords if isinstance(keywords, list) else [],
            "word_count": signals_payload.get("word_count"),
        },
        "signals": {
            "path": str(signals_path),
            "hash": _hash_file(signals_path),
            "top_evidence": evidence_items[:5],
        },
        "base_variant": base_variant_id,
        "draft_variant": draft_variant_id,
        "instructions": "Generate a tailored variant and patch proposal.",
        "proposal_plan": {
            "focus_keywords": (keywords[:5] if isinstance(keywords, list) else []),
            "steps": [
                "Review the copied job context and focus on the strongest repeated keywords.",
                "Draft only SoT-backed variant or patch changes.",
                "Prefer explicit patch operations over free-form rewrite notes.",
            ],
        },
        "model_id": None,
        "temperature": None,
        "diff_summary": None,
    }


def _build_signals(job_path: Path) -> dict[str, Any]:
    return build_job_signals(
        job_path.read_text(),
        {
            "type": "file",
            "value": str(job_path),
            "hash": _hash_file(job_path),
        },
    )


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
