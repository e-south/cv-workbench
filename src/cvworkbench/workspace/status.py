"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/status.py

Compose validated-source status and artifact inventories without terminal output.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from cvworkbench.config import (
    ConfigSource,
    read_config,
    resolve_sot_path,
    resolve_variant_ttl_days,
)
from cvworkbench.ops.variant_lifecycle import list_variant_inbox
from cvworkbench.variants import load_variants_from_config
from cvworkbench.workspace.projects import build_projects_context
from cvworkbench.workspace.publication import inspect_workspace_publication
from cvworkbench.workspace.reviews import build_reviews_context
from cvworkbench.workspace.runs import build_runs_context
from cvworkbench.workspace.source import build_sot_details, build_versions_info, inspect_source
from cvworkbench.workspace.variants import (
    inbox_entry_payload,
    inbox_summary_line,
    variants_summary_line,
)


class StatusInspectionError(ValueError):
    def __init__(self, errors: tuple[str, ...]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


def inspect_status(*, config: ConfigSource, sot_path: Path | None) -> dict[str, Any]:
    """Return source and inventory data, raising structured source diagnostics on failure."""
    configuration = read_config(config)
    resolved_sot = resolve_sot_path(sot_path, configuration)
    inspection = inspect_source(resolved_sot)
    if inspection.errors:
        raise StatusInspectionError(tuple(inspection.errors))
    sot_details = build_sot_details(resolved_sot, inspection.payload or {})
    versions_info, versions_summary, versions_error = build_versions_info(resolved_sot)
    if versions_error:
        raise StatusInspectionError((versions_error,))

    variants = load_variants_from_config(configuration.path)
    inbox_entries = list_variant_inbox(configuration)
    inbox_payload = [inbox_entry_payload(entry, configuration) for entry in inbox_entries]
    ttl_days = resolve_variant_ttl_days(configuration)
    runs_section, _ = build_runs_context(configuration, variants, include_recents=True)
    projects_section, _ = build_projects_context(configuration, include_items=True)
    reviews_section = build_reviews_context(configuration, include_items=True)
    return {
        "publication": asdict(inspect_workspace_publication(configuration, sot_path=sot_path)),
        "sot": {
            "path": str(resolved_sot),
            **sot_details,
            "versions": versions_info,
            "versions_summary": versions_summary,
        },
        "variants": {
            "config": variants,
            "config_count": len(variants),
            "summary": variants_summary_line(variants),
            "inbox": inbox_payload,
            "inbox_count": len(inbox_payload),
            "inbox_summary": inbox_summary_line(inbox_payload),
            "ttl_days": ttl_days,
        },
        "runs": runs_section,
        "projects": projects_section,
        "reviews": reviews_section,
    }
