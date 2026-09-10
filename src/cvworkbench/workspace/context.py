"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/context.py

Compose read-only workspace inventories, issues, and recommended workflows.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cvworkbench.config import (
    ConfigSnapshot,
    ConfigSource,
    load_config,
    read_config,
    resolve_default_variant,
    resolve_project_root,
    resolve_sot_path,
    resolve_variant_ttl_days,
)
from cvworkbench.ops.runs import (
    RunError,
)
from cvworkbench.ops.variant_lifecycle import (
    VariantLifecycleError,
    list_variant_inbox,
)
from cvworkbench.variants import load_variants_from_config
from cvworkbench.workspace.commands import command_prefix
from cvworkbench.workspace.projects import build_projects_context
from cvworkbench.workspace.publication import inspect_workspace_publication, publication_recipe
from cvworkbench.workspace.reviews import build_reviews_context
from cvworkbench.workspace.runs import build_runs_context
from cvworkbench.workspace.source import (
    build_sot_details,
    build_versions_info,
    configured_sot_path,
    inspect_source,
    sample_sot_path,
)
from cvworkbench.workspace.variants import (
    inbox_entry_payload,
    inbox_summary_line,
    variants_summary_line,
)
from cvworkbench.workspace.workflows.catalog import build_context_recipes
from cvworkbench.workspace.workflows.recommendations import build_recommended_workflows


@dataclass(frozen=True)
class ContextSharedState:
    configuration: ConfigSnapshot
    project_name: str | None
    configured_sot: str | None
    resolved_sot: Path | None
    sot_status: str
    sot_errors: list[str]
    sot_details: dict[str, Any]
    versions_info: dict[str, Any] | None
    versions_summary: str
    default_variant: str | None
    variants: list[dict[str, Any]]
    variants_summary: str
    inbox_payload: list[dict[str, Any]]
    inbox_summary: str
    ttl_days: int | None
    sample_sot: Path | None
    issues: list[str]

    @property
    def config_path(self) -> Path:
        return self.configuration.path


def _build_context_shared_state(
    *,
    sot_path: Path | None,
    strict: bool,
    config: ConfigSource,
) -> ContextSharedState:
    configuration = read_config(config)
    config_path = configuration.path
    config_payload = load_config(configuration)

    issues: list[str] = []
    configured_sot = configured_sot_path(configuration)
    resolved_sot: Path | None = None
    sot_errors: list[str] = []
    sot_details = {
        "files": [],
        "files_summary": "none",
        "sections": {},
        "sections_summary": "none",
        "tags_top": [],
        "tags_summary": "none",
    }
    versions_info: dict[str, Any] | None = None
    versions_summary = ""

    try:
        resolved_sot = resolve_sot_path(sot_path, configuration)
    except (FileNotFoundError, ValueError) as exc:
        _record_context_issue(str(exc), issues, strict)
        sot_errors.append(str(exc))

    if resolved_sot is not None and not resolved_sot.exists():
        message = f"SoT path not found: {resolved_sot}"
        _record_context_issue(message, issues, strict)
        sot_errors.append(message)
        resolved_sot = None

    sot_status = "missing"
    if resolved_sot is not None:
        inspection = inspect_source(resolved_sot)
        if inspection.errors:
            for error in inspection.errors:
                _record_context_issue(error, issues, strict)
                sot_errors.append(error)
            sot_status = "invalid"
        else:
            payload = inspection.payload or {}
            sot_details = build_sot_details(resolved_sot, payload)
            versions_info, versions_summary, versions_error = build_versions_info(resolved_sot)
            if versions_error:
                _record_context_issue(versions_error, issues, strict)
            sot_status = "ready"

    default_variant: str | None = None
    try:
        default_variant = resolve_default_variant(configuration)
    except ValueError as exc:
        _record_context_issue(str(exc), issues, strict)

    variants: list[dict[str, Any]] = []
    try:
        variants = load_variants_from_config(config_path)
    except ValueError as exc:
        _record_context_issue(str(exc), issues, strict)
    variants_summary = variants_summary_line(variants) if variants else "none"

    inbox_payload: list[dict[str, Any]] = []
    try:
        inbox_entries = list_variant_inbox(configuration)
        inbox_payload = [inbox_entry_payload(entry, configuration) for entry in inbox_entries]
    except (VariantLifecycleError, ValueError) as exc:
        _record_context_issue(str(exc), issues, strict)
    inbox_summary = inbox_summary_line(inbox_payload)

    ttl_days: int | None = None
    try:
        ttl_days = resolve_variant_ttl_days(configuration)
    except ValueError as exc:
        _record_context_issue(str(exc), issues, strict)

    project_name: str | None = None
    project_data = config_payload.get("project", {})
    if isinstance(project_data, dict):
        name_value = project_data.get("name")
        if isinstance(name_value, str) and name_value.strip():
            project_name = name_value.strip()

    return ContextSharedState(
        configuration=configuration,
        project_name=project_name,
        configured_sot=configured_sot,
        resolved_sot=resolved_sot,
        sot_status=sot_status,
        sot_errors=sot_errors,
        sot_details=sot_details,
        versions_info=versions_info,
        versions_summary=versions_summary,
        default_variant=default_variant,
        variants=variants,
        variants_summary=variants_summary,
        inbox_payload=inbox_payload,
        inbox_summary=inbox_summary,
        ttl_days=ttl_days,
        sample_sot=sample_sot_path(configuration),
        issues=issues,
    )


def _record_context_issue(message: str, issues: list[str], strict: bool) -> None:
    if strict:
        raise ValueError(message)
    issues.append(message)


def inspect_workspace(
    *,
    sot_path: Path | None,
    strict: bool,
    config: ConfigSource,
    compact: bool = False,
) -> dict[str, Any]:
    """Inspect local state without terminal output or workspace writes.

    Strict inspection raises ValueError for a recoverable inspection issue.
    Configuration failures remain exceptions in either mode.
    """
    shared = _build_context_shared_state(sot_path=sot_path, strict=strict, config=config)

    latest_payload: dict[str, list[dict[str, Any]]] = {}
    runs_section: dict[str, Any] = {
        "latest_summary": "none",
        "invalid_summary": "",
    }
    try:
        runs_section, latest_payload = build_runs_context(
            shared.configuration,
            shared.variants,
            include_recents=not compact,
        )
    except (RunError, ValueError) as exc:
        _record_context_issue(str(exc), shared.issues, strict)

    projects: list[dict[str, Any]] = []
    projects_section: dict[str, Any] = {
        "count": 0,
        "summary": "count=0",
        "invalid_summary": "",
    }
    try:
        projects_section, projects = build_projects_context(
            shared.configuration,
            include_items=not compact,
        )
    except (ValueError, FileNotFoundError) as exc:
        _record_context_issue(str(exc), shared.issues, strict)

    reviews_section: dict[str, Any] = {
        "count": 0,
        "summary": "count=0",
    }
    try:
        reviews_section = build_reviews_context(shared.configuration, include_items=not compact)
    except (ValueError, FileNotFoundError) as exc:
        _record_context_issue(str(exc), shared.issues, strict)

    recipe_sot_path = sot_path if sot_path is not None else shared.resolved_sot
    recipe_configured_sot = None if sot_path is not None else shared.configured_sot

    recipes = build_context_recipes(
        config_path=shared.config_path,
        workspace_root=resolve_project_root(shared.configuration),
        sot_path=recipe_sot_path,
        configured_sot_path=recipe_configured_sot,
        sot_status=shared.sot_status,
        sample_sot_path=shared.sample_sot,
        default_variant=shared.default_variant,
    )

    publication = inspect_workspace_publication(shared.configuration, sot_path=sot_path)
    recipes.append(
        publication_recipe(
            publication,
            config_path=shared.config_path,
            command_prefix=command_prefix(),
            sot_path=sot_path,
        )
    )

    return {
        "config": {
            "path": str(shared.config_path),
            "project": {"name": shared.project_name},
        },
        "sot": {
            "configured_path": shared.configured_sot,
            "path": str(shared.resolved_sot) if shared.resolved_sot else None,
            "status": shared.sot_status,
            "errors": shared.sot_errors,
            "versions": shared.versions_info,
            "versions_summary": shared.versions_summary,
            **shared.sot_details,
        },
        "variants": {
            "config": shared.variants,
            "config_count": len(shared.variants),
            "summary": shared.variants_summary,
            "inbox": shared.inbox_payload,
            "inbox_count": len(shared.inbox_payload),
            "inbox_summary": shared.inbox_summary,
            "ttl_days": shared.ttl_days,
            "default": shared.default_variant,
        },
        "runs": runs_section,
        "projects": projects_section,
        "reviews": reviews_section,
        "publication": asdict(publication),
        "recipes": recipes,
        "recommended_workflows": build_recommended_workflows(
            recipes=recipes,
            sot_status=shared.sot_status,
            latest_runs=latest_payload,
            default_variant=shared.default_variant,
            config_path=shared.config_path,
            sot_path=sot_path,
            publication=publication,
        ),
        "issues": shared.issues,
    }
