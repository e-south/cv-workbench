"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/variant_promote.py

Promotes draft variants into the canonical variants directory.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from cvworkbench.config import resolve_variant_path


class PromoteError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromoteResult:
    variant_id: str
    variant_path: Path
    status: str


def promote_variant(
    *,
    draft_dir: Path,
    config_path: Path,
    variant_id: str | None,
) -> PromoteResult:
    if not draft_dir.exists():
        raise PromoteError(f"Draft directory not found: {draft_dir}")

    draft_variant_path = draft_dir / "variant.yaml"
    if not draft_variant_path.exists():
        raise PromoteError(f"Draft variant not found: {draft_variant_path}")

    raw = yaml.safe_load(draft_variant_path.read_text())
    if raw is None or not isinstance(raw, dict):
        raise PromoteError("Draft variant is invalid")

    variant_section = raw.get("variant")
    if not isinstance(variant_section, dict):
        raise PromoteError("Draft variant must contain a 'variant' mapping")

    draft_id = variant_section.get("id")
    if not isinstance(draft_id, str) or not draft_id.strip():
        raise PromoteError("Draft variant id is required")

    resolved_id = variant_id.strip() if variant_id else draft_id.strip()
    if not resolved_id:
        raise PromoteError("Variant id is required")

    variant_section["id"] = resolved_id

    target_path = resolve_variant_path(resolved_id, config_path)
    if target_path.exists():
        raise PromoteError(f"Variant already exists: {target_path}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(yaml.safe_dump(raw, sort_keys=False))

    return PromoteResult(
        variant_id=resolved_id,
        variant_path=target_path,
        status="created",
    )
