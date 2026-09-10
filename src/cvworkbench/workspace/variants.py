"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/variants.py

Describe configured variants and proposal inbox lifecycle state.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cvworkbench.config import ConfigSource, resolve_config_path
from cvworkbench.ops.projects import (
    suggest_project_variant_id,
)
from cvworkbench.variants import load_variant
from cvworkbench.workspace.commands import recipe_command


def _variants_dir(config_path: Path) -> Path:
    return config_path.parent / "variants"


def load_variants_from_config(config_path: Path) -> list[dict[str, Any]]:
    variants_dir = _variants_dir(config_path)
    if not variants_dir.exists():
        raise ValueError(f"Variants directory not found: {variants_dir}")
    variants: list[dict[str, Any]] = []
    for path in sorted(variants_dir.glob("*.yaml")):
        variant = load_variant(path)
        variants.append(
            {
                "id": variant.id,
                "document_type": variant.document_type,
                "outputs": variant.outputs,
                "include_tags": variant.include_tags,
                "exclude_tags": variant.exclude_tags,
                "letter_id": variant.letter_id,
                "render_theme": variant.render_theme,
                "render_style_preset": variant.render_style_preset,
                "max_bullets_per_role": variant.max_bullets_per_role,
                "path": str(path),
            }
        )
    if not variants:
        raise ValueError("No variants found")
    return variants


def variants_summary_line(variants: list[dict[str, Any]]) -> str:
    return ", ".join([f"{variant['id']} ({variant['document_type']})" for variant in variants])


def _parse_iso_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _inbox_display_status(entry: Any) -> tuple[str, bool]:
    expires_at = _parse_iso_timestamp(entry.expires_at)
    if (
        entry.status == "ephemeral"
        and expires_at is not None
        and expires_at <= datetime.now(timezone.utc)
    ):
        return "expired_pending_gc", True
    return entry.status, False


def inbox_entry_payload(entry: Any, config_path: ConfigSource) -> dict[str, Any]:
    configuration = config_path
    config_path = resolve_config_path(configuration)
    project_id = _project_id_from_variant_entry_path(entry.variant_path)
    selector_kind = "project" if entry.source == "project" and project_id else "path"
    selector = project_id if selector_kind == "project" else str(entry.variant_path)
    display_status, expired = _inbox_display_status(entry)
    payload = {
        "variant_id": entry.variant_id,
        "variant_path": str(entry.variant_path),
        "cleanup_path": str(entry.cleanup_path),
        "source": entry.source,
        "status": display_status,
        "registry_status": entry.status,
        "expired": expired,
        "expires_at": entry.expires_at,
        "label": entry.label,
        "selector_kind": selector_kind,
        "selector": selector,
        "project_id": project_id,
    }
    if selector_kind == "project" and project_id is not None:
        patch_root = entry.cleanup_path
        if patch_root.name != "proposals":
            patch_root = patch_root / "proposals"
        payload["patch_path"] = str(patch_root / "patch.yaml")
        keep_variant_id = suggest_project_variant_id(
            project_id=project_id,
            config_path=configuration,
            preferred_id=entry.variant_id,
        )
        payload["keep_command"] = recipe_command(
            f"variant keep --project {shlex.quote(project_id)} --id {shlex.quote(keep_variant_id)}",
            config_path=config_path,
            sot_path=None,
        )
        payload["discard_command"] = recipe_command(
            f"variant discard --project {shlex.quote(project_id)} --yes",
            config_path=config_path,
            sot_path=None,
        )
        payload["preview_command"] = recipe_command(
            f"preview --project {shlex.quote(project_id)}",
            config_path=config_path,
            sot_path=None,
        )
        return payload

    payload["keep_command"] = recipe_command(
        shlex.join(
            [
                "variant",
                "keep",
                "--path",
                str(entry.variant_path),
                "--id",
                entry.variant_id,
            ]
        ),
        config_path=config_path,
        sot_path=None,
    )
    payload["discard_command"] = recipe_command(
        shlex.join(
            [
                "variant",
                "discard",
                "--path",
                str(entry.variant_path),
                "--yes",
            ]
        ),
        config_path=config_path,
        sot_path=None,
    )
    return payload


def _project_id_from_variant_entry_path(path: Path) -> str | None:
    parts = path.parts
    for index in range(len(parts) - 2):
        if parts[index] == "var" and parts[index + 1] == "projects":
            return parts[index + 2]
    return None


def inbox_summary_line(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "count=0"
    lines = [
        f"{entry['label'] or entry['variant_id']} | {entry['source']} | {entry['status']} | {entry['expires_at']}"
        for entry in entries
    ]
    return f"count={len(entries)}\n" + "\n".join(lines)
