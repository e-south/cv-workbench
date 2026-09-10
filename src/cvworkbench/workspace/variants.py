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

from cvworkbench.config import ConfigSource, read_config
from cvworkbench.ops.projects import (
    ProjectError,
    load_project_metadata,
    suggest_project_variant_id,
)
from cvworkbench.workspace.commands import recipe_command
from cvworkbench.workspace.projects.commands import project_selector


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
    configuration = read_config(config_path)
    config_path = configuration.path
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
        "selector_kind": "path",
        "selector": str(entry.variant_path),
        "project_id": None,
    }
    if entry.source == "project":
        try:
            payload.update(_inbox_project(entry.variant_path, configuration))
        except ProjectError as exc:
            payload["project_error"] = str(exc)
    if payload["selector_kind"] == "project":
        selector = shlex.quote(payload["selector"])
        keep_variant_id = suggest_project_variant_id(
            project_id=payload["project_id"],
            config_path=configuration,
            preferred_id=entry.variant_id,
        )
        payload["keep_command"] = recipe_command(
            f"variant keep --project {selector} --id {shlex.quote(keep_variant_id)}",
            config_path=config_path,
            sot_path=None,
        )
        payload["discard_command"] = recipe_command(
            f"variant discard --project {selector} --yes",
            config_path=config_path,
            sot_path=None,
        )
        payload["preview_command"] = recipe_command(
            f"preview --project {selector}",
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


def _inbox_project(path: Path, config_path: ConfigSource) -> dict[str, Any]:
    if path.name != "variant.yaml" or path.parent.name != "proposals":
        raise ProjectError("Project proposal must be located at proposals/variant.yaml")
    project_dir = path.parent.parent
    project_id = load_project_metadata(project_dir)["id"]
    return {
        "selector_kind": "project",
        "selector": project_selector(project_id, project_dir=project_dir, config_path=config_path),
        "project_id": project_id,
        "project_dir": str(project_dir),
        "patch_path": str(path.parent / "patch.yaml"),
    }


def inbox_summary_line(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "count=0"
    lines = [
        f"{entry['label'] or entry['variant_id']} | {entry['source']} | {entry['status']} | {entry['expires_at']}"
        + (f" | project_error: {entry['project_error']}" if "project_error" in entry else "")
        for entry in entries
    ]
    return f"count={len(entries)}\n" + "\n".join(lines)
