"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/app.py

Command-line interface for the CV workbench.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import ipaddress
import json
import os
import signal
import socket
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any
from urllib import error as url_error
from urllib import request as url_request

import typer

from cvworkbench.build.explain import ExplainError, explain_item, load_selection
from cvworkbench.build.formats import normalize_output_formats
from cvworkbench.build.paths import filters_dir, output_path
from cvworkbench.build.pipeline import BuildResult, build_documents, create_run_dir
from cvworkbench.build.rendering import (
    RenderError,
    RenderRequest,
    render_documents,
    resolve_filter_paths,
)
from cvworkbench.build.styles import prepare_html_style
from cvworkbench.cli.helpers import configure_output_mode, load_sot_payload, resolve_selection_path
from cvworkbench.cli.output import OutputMode, get_output_mode, print_summary
from cvworkbench.cli.publication import prepare_public_pdf_command, publication_app, sync
from cvworkbench.config import (
    read_config,
    resolve_config_path,
    resolve_default_theme,
    resolve_default_variant,
    resolve_dist_path,
    resolve_drafts_path,
    resolve_pdf_engine,
    resolve_project_path,
    resolve_project_root,
    resolve_projects_path,
    resolve_registry_path,
    resolve_reviews_path,
    resolve_runs_path,
    resolve_sot_path,
    resolve_style_preset,
    resolve_themes_dir,
    resolve_var_root,
    resolve_variant_path,
    resolve_variant_ttl_days,
)
from cvworkbench.ingestion.registry import RegistryError, add_url_context
from cvworkbench.inputs.sot import load_sot
from cvworkbench.inputs.sot_versions import (
    SotVersionError,
    resolve_active_sot_path,
    resolve_versioned_root,
)
from cvworkbench.inputs.tags import extract_tags, lint_tags, tag_counts
from cvworkbench.ops.apply import ApplyError, apply_draft
from cvworkbench.ops.clean import CleanError, clean_path
from cvworkbench.ops.diffing import DiffError, DiffSelection, diff_artifacts, parse_artifact
from cvworkbench.ops.doctor import run_doctor
from cvworkbench.ops.projects import (
    ProjectError,
    append_replace_experience_bullet_operation,
    append_replace_project_summary_operation,
    apply_project_patch,
    create_project_from_file,
    create_project_from_url,
    discard_project_workspace,
    load_project,
    load_project_details,
    prepare_project_sot,
    project_patch_render_warning,
    project_patch_status,
    resolve_project_dir,
    retarget_project_variant,
)
from cvworkbench.ops.render_compare import RenderCompareError, compare_rendered_pdfs
from cvworkbench.ops.review import ReviewError
from cvworkbench.ops.review.importing import import_docx_review
from cvworkbench.ops.review.packs import build_review_pack
from cvworkbench.ops.review.record import SOURCE_RECORD_NAME
from cvworkbench.ops.runs import (
    RunError,
    RunGcCandidate,
    RunGcSummary,
    gc_runs,
)
from cvworkbench.ops.scaffold import ScaffoldError, init_project, resolve_template_root
from cvworkbench.ops.sot_versions import (
    SotPackError,
    activate_version,
    create_version,
    diff_versions,
    list_versions,
)
from cvworkbench.ops.tailor import DraftPaths, TailorError, tailor_job
from cvworkbench.ops.variant_lifecycle import (
    VariantGcSummary,
    VariantLifecycleError,
    discard_variant,
    gc_variants,
    keep_variant,
    list_variant_inbox,
)
from cvworkbench.ops.variant_promote import PromoteError, promote_variant
from cvworkbench.themes import (
    ThemeError,
    build_render_plan,
    list_theme_presets,
    list_themes,
    resolve_theme,
)
from cvworkbench.variants import load_variant
from cvworkbench.workspace.commands import recipe_command, shell_command
from cvworkbench.workspace.context import inspect_workspace
from cvworkbench.workspace.project_guidance import (
    build_job_evidence,
    build_proposal_plan,
    job_keyword_overlap,
    job_signal_counts,
    load_job_signals,
    load_optional_json,
    normalize_keywords,
    recommend_variants,
    recommendations_summary_line,
)
from cvworkbench.workspace.projects import (
    project_commands,
    project_review_payload,
)
from cvworkbench.workspace.runs import (
    run_payload,
)
from cvworkbench.workspace.source import (
    tags_summary_line,
    top_tags,
)
from cvworkbench.workspace.status import StatusInspectionError, inspect_status
from cvworkbench.workspace.variants import (
    inbox_entry_payload,
    inbox_summary_line,
    load_variants_from_config,
    variants_summary_line,
)

if TYPE_CHECKING:
    from cvworkbench.dev.preview import PreviewSession

app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(
    publication_app,
    name="publication",
    help="Inspect authored publication freshness and record exact-PDF review.",
)
app.command("prepare-public-pdf")(prepare_public_pdf_command)
app.command("sync")(sync)
job_app = typer.Typer(no_args_is_help=True)
tags_app = typer.Typer(no_args_is_help=True)
theme_app = typer.Typer(no_args_is_help=True)
dev_app = typer.Typer(no_args_is_help=True)
variant_app = typer.Typer(no_args_is_help=True)
clean_app = typer.Typer(no_args_is_help=True)
sot_app = typer.Typer(no_args_is_help=True)
project_app = typer.Typer(no_args_is_help=True)
project_patch_app = typer.Typer(no_args_is_help=True)
runs_app = typer.Typer(no_args_is_help=True)
app.add_typer(job_app, name="job", help="Ingest and inspect job-posting context sources.")
app.add_typer(tags_app, name="tags", help="List, lint, and summarize SoT tags.")
app.add_typer(theme_app, name="theme", help="Inspect available render themes and presets.")
app.add_typer(dev_app, name="dev", help="Control the local preview server lifecycle.")
app.add_typer(
    variant_app,
    name="variant",
    help="Inspect configured variants and manage ephemeral draft/project proposals.",
)
app.add_typer(runs_app, name="runs", help="Inspect or prune build runs.")
app.add_typer(clean_app, name="clean", help="Remove generated workspace artifacts.")
app.add_typer(sot_app, name="sot", help="Inspect and manage SoT version packs.")
app.add_typer(
    project_app,
    name="project",
    help="Create, inspect, and apply job-tailoring project workspaces.",
)
project_app.add_typer(
    project_patch_app,
    name="patch",
    help="Author validated project-op edits without hand-editing patch.yaml.",
)


def _not_implemented(command: str) -> None:
    typer.echo(f"{command} is not implemented yet", err=True)
    raise typer.Exit(code=2)


def _validate_sot(sot_path: Path) -> list[str]:
    from cvworkbench.inputs.validation import validate_sot

    return validate_sot(sot_path)


def _preview_runtime():
    from cvworkbench.dev import preview as preview_runtime

    return preview_runtime


def serve_preview(*args, **kwargs):
    return _preview_runtime().serve_preview(*args, **kwargs)


def _parse_formats(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    formats: list[str] = []
    for value in values:
        parts = [part.strip() for part in value.split(",") if part.strip()]
        formats.extend(parts)
    normalized = normalize_output_formats(formats)
    return [] if normalized is None else normalized


def _print_build_summary(result: BuildResult) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("variant", result.variant.id),
        ("formats", ",".join(result.formats)),
        ("outputs_dir", result.dist_dir),
        ("run_dir", result.run_dir),
        ("canonical", result.canonical_path),
        ("resume_json", result.run_dir / "resume.json"),
        ("manifest_dist", result.dist_dir / "manifest.json"),
        ("manifest_run", result.run_dir / "manifest.json"),
    ]
    if result.theme_id:
        rows.append(("theme", result.theme_id))
    if result.style_preset:
        rows.append(("style_preset", result.style_preset))
    for fmt in result.formats:
        output_file = output_path(result.dist_dir, result.variant, fmt)
        rows.append((f"output_{fmt}", output_file))
    print_summary("build", rows)


def _print_render_summary(
    canonical: Path,
    variant: str,
    dist_dir: Path,
    outputs: dict[str, Path],
) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("variant", variant),
        ("outputs_dir", dist_dir),
        ("canonical", canonical),
    ]
    for fmt, path in outputs.items():
        rows.append((f"output_{fmt}", path))
    print_summary("render", rows)


def _print_validate_summary(sot_path: Path) -> None:
    print_summary(
        "validate",
        [
            ("status", "ok"),
            ("sot_path", sot_path),
        ],
    )


def _print_diff_summary(summary: dict[str, Any]) -> None:
    side_a = summary.get("a", {})
    side_b = summary.get("b", {})
    rows: list[tuple[str, str | Path]] = [
        ("artifact_a", str(side_a.get("artifact", ""))),
        ("artifact_b", str(side_b.get("artifact", ""))),
        ("path_a", str(side_a.get("path", ""))),
        ("path_b", str(side_b.get("path", ""))),
        ("equal", str(summary.get("equal", ""))),
        ("additions", str(summary.get("additions", ""))),
        ("deletions", str(summary.get("deletions", ""))),
    ]
    print_summary("diff", rows)


def _print_compare_summary(summary: dict[str, Any]) -> None:
    run_a = summary.get("run_a", {})
    run_b = summary.get("run_b", {})
    rows: list[tuple[str, str | Path]] = [
        ("run_a", str(run_a.get("run_id", ""))),
        ("run_b", str(run_b.get("run_id", ""))),
        ("pdf_a", str(run_a.get("pdf", ""))),
        ("pdf_b", str(run_b.get("pdf", ""))),
        ("status", str(summary.get("status", ""))),
        ("page_count_a", str(summary.get("page_count_a", ""))),
        ("page_count_b", str(summary.get("page_count_b", ""))),
        ("identical_pages", str(summary.get("identical_pages", ""))),
        ("different_pages", str(summary.get("different_pages", ""))),
        ("report", str(summary.get("report", ""))),
        ("summary_json", str(summary.get("summary_json", ""))),
    ]
    print_summary("compare", rows)


def _print_doctor_summary(rows: list[tuple[str, str | Path]]) -> None:
    print_summary("doctor", rows)


def _print_init_summary(result: dict[str, str | Path]) -> None:
    rows = [(key, value) for key, value in result.items()]
    print_summary("init", rows)


def _print_job_add_summary(entry: dict[str, str | Path]) -> None:
    rows = [(key, value) for key, value in entry.items()]
    print_summary("job.add", rows)


def _print_explain_summary(item: dict[str, Any]) -> None:
    reasons = item.get("reasons") or []
    tags = item.get("tags") or []
    rows: list[tuple[str, str | Path]] = [
        ("id", str(item.get("id", ""))),
        ("type", str(item.get("type", ""))),
        ("included", str(item.get("included", ""))),
        ("reasons", ", ".join(reasons)),
        ("tags", ", ".join(tags)),
    ]
    if "text" in item and item.get("text"):
        rows.append(("text", str(item.get("text"))))
    if "label" in item and item.get("label"):
        rows.append(("label", str(item.get("label"))))
    if "role_id" in item:
        rows.append(("role_id", str(item.get("role_id"))))
    if "section" in item:
        rows.append(("section", str(item.get("section"))))
    print_summary("explain", rows)


def _print_reviewpack_summary(summary: dict[str, str | Path]) -> None:
    rows = [(key, value) for key, value in summary.items()]
    print_summary("reviewpack", rows)


def _print_import_summary(summary: dict[str, str | Path]) -> None:
    rows = [(key, value) for key, value in summary.items()]
    print_summary("import-docx", rows)


def _print_status_summary(summary: dict[str, Any]) -> None:
    rows = [
        ("sot_path", summary["sot"]["path"]),
        ("sot_files", summary["sot"]["files_summary"]),
        ("sot_sections", summary["sot"]["sections_summary"]),
        ("sot_tags_top", summary["sot"]["tags_summary"]),
        ("variants", summary["variants"]["summary"]),
        ("variant_inbox", summary["variants"]["inbox_summary"]),
        ("variant_ttl_days", summary["variants"]["ttl_days"]),
        ("runs_latest", summary["runs"]["latest_summary"]),
        ("runs_recent", summary["runs"]["recents_summary"]),
        ("projects", summary["projects"]["summary"]),
        ("publication", summary["publication"]["state"]),
        ("reviews", summary["reviews"]["summary"]),
    ]
    if summary["runs"]["invalid_summary"]:
        rows.append(("runs_invalid", summary["runs"]["invalid_summary"]))
    if summary["projects"]["invalid_summary"]:
        rows.append(("projects_invalid", summary["projects"]["invalid_summary"]))
    if summary["sot"]["versions_summary"]:
        rows.append(("sot_versions", summary["sot"]["versions_summary"]))
    print_summary("status", rows)


def _print_context_summary(summary: dict[str, Any]) -> None:
    sot_path = summary["sot"]["path"] or summary["sot"]["configured_path"] or "none"
    recommended = summary["recommended_workflows"]
    rows = [
        ("config", summary["config"]["path"]),
        ("publication", summary["publication"]["state"]),
        ("sot_status", summary["sot"]["status"]),
        ("sot_path", sot_path),
        ("variants", summary["variants"]["summary"]),
        ("runs_latest", summary["runs"]["latest_summary"]),
        ("projects", summary["projects"]["summary"]),
        ("reviews", summary["reviews"]["summary"]),
        (
            "next_workflows",
            ", ".join([workflow["id"] for workflow in recommended]) or "none",
        ),
        (
            "next_commands",
            "\n".join([f"{workflow['id']}: {workflow['command']}" for workflow in recommended])
            or "none",
        ),
        ("recipes", ", ".join([recipe["id"] for recipe in summary["recipes"]])),
    ]
    if summary["issues"]:
        rows.append(("issues", "; ".join(summary["issues"])))
    print_summary("context", rows)


def _print_bootstrap_summary(summary: dict[str, Any]) -> None:
    sot_path = summary["sot"]["path"] or summary["sot"]["configured_path"] or "none"
    recommended = summary["recommended_workflows"]
    rows = [
        ("config", summary["config"]["path"]),
        ("sot_status", summary["sot"]["status"]),
        ("sot_path", sot_path),
        ("variants", summary["variants"]["summary"]),
        ("runs_latest", summary["runs"]["latest_summary"]),
        (
            "next_workflows",
            ", ".join([workflow["id"] for workflow in recommended]) or "none",
        ),
        (
            "next_commands",
            "\n".join([f"{workflow['id']}: {workflow['command']}" for workflow in recommended])
            or "none",
        ),
    ]
    if summary["issues"]:
        rows.append(("issues", "; ".join(summary["issues"])))
    print_summary("bootstrap", rows)


def _format_workflow_list(items: list[str]) -> str:
    if not items:
        return "none"
    return "\n".join(f"- {item}" for item in items)


def _format_workflow_steps(steps: list[dict[str, Any]]) -> str:
    if not steps:
        return "none"
    lines: list[str] = []
    for index, step in enumerate(steps, start=1):
        lines.append(f"{index}. {step['command']}")
        description = step.get("description")
        if description:
            lines.append(f"   {description}")
    return "\n".join(lines)


def _resolve_variant_lifecycle_path(
    *,
    path: Path | None,
    project: str | None,
    config_path: Path,
) -> Path:
    if (path is None) == (project is None):
        raise ValueError("Provide exactly one of --path or --project")
    if project is None:
        return path or Path()
    project_dir = resolve_project_dir(project, config_path)
    spec = load_project(project_dir)
    return spec.variant_path


def _print_workflow_summary(
    *,
    recipes: list[dict[str, Any]],
    sot_status: str,
    issues: list[str],
    selected_recipe: str | None,
) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("sot_status", sot_status),
        ("recipes", str(len(recipes))),
    ]
    if selected_recipe:
        rows.append(("selected", selected_recipe))
    if issues:
        rows.append(("issues", "; ".join(issues)))
    print_summary("workflow", rows)

    for index, recipe in enumerate(recipes):
        print_summary(
            f"workflow.{recipe['id']}",
            [
                ("recipe_id", recipe["id"]),
                ("title", recipe["title"]),
                ("preconditions", _format_workflow_list(recipe["preconditions"])),
                ("steps", _format_workflow_steps(recipe["steps"])),
                ("outputs", _format_workflow_list(recipe["outputs"])),
                ("stop_conditions", _format_workflow_list(recipe["stop_conditions"])),
            ],
        )
        if get_output_mode() == OutputMode.PLAIN and index < len(recipes) - 1:
            print("")


def _compact_context_payload(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "config": summary["config"],
        "publication": summary["publication"],
        "sot": {
            "configured_path": summary["sot"]["configured_path"],
            "path": summary["sot"]["path"],
            "status": summary["sot"]["status"],
            "errors": summary["sot"]["errors"],
            "files_summary": summary["sot"]["files_summary"],
            "sections_summary": summary["sot"]["sections_summary"],
            "tags_summary": summary["sot"]["tags_summary"],
            "versions_summary": summary["sot"]["versions_summary"],
        },
        "variants": {
            "default": summary["variants"]["default"],
            "config_count": summary["variants"]["config_count"],
            "summary": summary["variants"]["summary"],
            "inbox_count": summary["variants"]["inbox_count"],
            "inbox_summary": summary["variants"]["inbox_summary"],
            "ttl_days": summary["variants"]["ttl_days"],
        },
        "runs": {
            "latest_summary": summary["runs"]["latest_summary"],
            "invalid_summary": summary["runs"]["invalid_summary"],
        },
        "projects": {
            "count": summary["projects"]["count"],
            "summary": summary["projects"]["summary"],
            "invalid_summary": summary["projects"]["invalid_summary"],
        },
        "reviews": {
            "count": summary["reviews"]["count"],
            "summary": summary["reviews"]["summary"],
        },
        "recipes": [
            {"id": recipe["id"], "title": recipe["title"]} for recipe in summary["recipes"]
        ],
        "recommended_workflows": summary["recommended_workflows"],
        "issues": summary["issues"],
    }


def _compact_workflow_payload(
    summary: dict[str, Any], recipes: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "config": summary["config"],
        "sot": {
            "configured_path": summary["sot"]["configured_path"],
            "path": summary["sot"]["path"],
            "status": summary["sot"]["status"],
            "errors": summary["sot"]["errors"],
        },
        "recipes": recipes,
        "issues": summary["issues"],
    }


def _run_gc_candidate_payload(candidate: RunGcCandidate) -> dict[str, Any]:
    return {
        "run_id": candidate.run_id,
        "path": str(candidate.path),
        "variant_id": candidate.variant_id,
        "created_at": candidate.created_at.isoformat(),
        "reason": candidate.reason,
    }


def _print_runs_gc_summary(summary: RunGcSummary, keep_latest: int, include_invalid: bool) -> None:
    rows = [
        ("status", summary.status),
        ("keep_latest", str(keep_latest)),
        ("candidates", str(len(summary.candidates))),
        ("kept", str(len(summary.kept))),
        ("removed", str(summary.removed)),
    ]
    if include_invalid:
        rows.append(("invalid", str(len(summary.invalid))))
        rows.append(("invalid_candidates", str(len(summary.invalid_candidates))))
    rows.append(
        (
            "retained",
            "\n".join(
                f"{run_id} | {', '.join(reasons)}"
                for run_id, reasons in summary.keep_reasons.items()
            )
            or "none",
        )
    )
    print_summary("runs.gc", rows)


def _proposal_plan_summary_rows(
    proposal_plan: dict[str, Any] | None,
    *,
    prefix: str = "",
) -> list[tuple[str, str]]:
    if not proposal_plan:
        return []
    step_values = proposal_plan.get("steps")
    steps: list[str] = []
    if isinstance(step_values, list):
        steps = [
            str(item).strip() for item in step_values if isinstance(item, str) and item.strip()
        ]
    missing_values = proposal_plan.get("job_keywords_missing_in_sot")
    missing_keywords: list[str] = []
    if isinstance(missing_values, list):
        missing_keywords = [
            str(item).strip() for item in missing_values if isinstance(item, str) and item.strip()
        ]
    rows = [
        (f"{prefix}recommended_variant", str(proposal_plan.get("selected_variant") or "none")),
        (f"{prefix}selection_mode", str(proposal_plan.get("selection_mode") or "unknown")),
        (f"{prefix}recommendation_status", str(proposal_plan.get("status") or "unknown")),
        (f"{prefix}recommendation_summary", str(proposal_plan.get("summary") or "none")),
        (f"{prefix}job_keywords_missing", ", ".join(missing_keywords) or "none"),
        (f"{prefix}proposal_steps", "\n".join(steps) or "none"),
    ]
    return rows


def _print_variant_promote_summary(variant_id: str, variant_path: Path, status: str) -> None:
    print_summary(
        "variant.promote",
        [
            ("variant_id", variant_id),
            ("variant_path", variant_path),
            ("status", status),
        ],
    )


def _print_variant_keep_summary(variant_id: str, variant_path: Path, status: str) -> None:
    print_summary(
        "variant.keep",
        [
            ("variant_id", variant_id),
            ("variant_path", variant_path),
            ("status", status),
        ],
    )


def _print_variant_discard_summary(variant_path: Path, status: str) -> None:
    print_summary(
        "variant.discard",
        [
            ("variant_path", variant_path),
            ("status", status),
        ],
    )


def _print_variant_gc_summary(summary: VariantGcSummary) -> None:
    candidates = [
        {**asdict(candidate), "cleanup_path": str(candidate.cleanup_path)}
        for candidate in summary.candidates
    ]
    if get_output_mode() == OutputMode.JSON:
        print(
            json.dumps(
                {"command": "variant.gc", **asdict(summary), "candidates": candidates},
                indent=2,
                sort_keys=True,
            )
        )
        return
    print_summary(
        "variant.gc",
        [
            ("expired", str(summary.expired)),
            ("kept_pruned", str(summary.kept_pruned)),
            ("reconciled", str(summary.reconciled)),
            ("status", summary.status),
            (
                "candidates",
                "\n".join(
                    f"{item.action} | {item.reason} | {item.variant_id} | {item.cleanup_path}"
                    for item in summary.candidates
                )
                or "none",
            ),
        ],
    )


def _print_variant_inbox(entries: list[Any], config_path: Path) -> None:
    entry_payload = [inbox_entry_payload(entry, config_path) for entry in entries]
    has_expired_entries = any(item["expired"] for item in entry_payload)
    if get_output_mode() == OutputMode.JSON:
        payload = {
            "command": "variant.inbox",
            "entries": entry_payload,
        }
        if has_expired_entries:
            payload["gc_command"] = recipe_command(
                "variant gc",
                config_path=config_path,
                sot_path=None,
            )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    lines = [
        (
            f"{item['variant_id']} | {item['source']} | {item['status']} | "
            f"{item['expires_at']} | {item['variant_path']}"
        )
        for item in entry_payload
    ]
    rows: list[tuple[str, str | Path]] = [
        ("count", str(len(entry_payload))),
    ]
    if lines:
        rows.append(("entries", "\n".join(lines)))
    if has_expired_entries:
        rows.append(("gc_step", shell_command("variant gc")))
    print_summary("variant.inbox", rows)


def _print_clean_summary(target: str, path: Path, removed: int, status: str) -> None:
    print_summary(
        "clean",
        [
            ("target", target),
            ("path", path),
            ("removed", str(removed)),
            ("status", status),
        ],
    )


def _print_theme_list_summary(theme_ids: list[str], default_theme: str) -> None:
    print_summary(
        "theme.list",
        [
            ("themes", ", ".join(theme_ids)),
            ("default", default_theme),
        ],
    )


def _print_theme_info_summary(
    theme_id: str,
    description: str | None,
    routes: list[str],
    presets: list[str],
) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("id", theme_id),
        ("routes", ", ".join(routes)),
        ("presets", ", ".join(presets) if presets else "none"),
    ]
    if description:
        rows.append(("description", description))
    print_summary("theme.info", rows)


def _print_serve_summary(
    output_path: Path,
    preview_url: str,
    watching: bool,
) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("output_html", output_path),
        ("watching", str(watching).lower()),
        ("controls", "t=theme p=preset v=variant f=format r=rebuild x=stop"),
    ]
    if watching:
        rows.insert(1, ("preview_url", preview_url))
    else:
        rows.insert(1, ("preview_file", output_path))
    print_summary("serve", rows)


def _reject_legacy_preview_env() -> None:
    legacy_vars = [
        "CVW_SKIP_OPEN",
        "CVW_PREVIEW_VIEWER",
        "CVW_OPEN_MODE",
        "CVW_BROWSER",
    ]
    for key in legacy_vars:
        if os.environ.get(key):
            typer.echo(
                f"ERROR: legacy preview environment variable is not supported: {key}",
                err=True,
            )
            raise typer.Exit(code=2)


def _validate_preview_host(host: str) -> str:
    normalized = host.strip()
    if not normalized:
        raise ValueError("CVW_DEV_HOST must not be empty")
    if normalized.lower() == "localhost":
        return normalized
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise ValueError(
            "CVW_DEV_HOST must be localhost or a loopback address; non-local preview binding is not supported"
        ) from exc
    if not address.is_loopback:
        raise ValueError(
            "CVW_DEV_HOST must be localhost or a loopback address; non-local preview binding is not supported"
        )
    return normalized


def _require_var_path(target: str, path: Path, config_path: Path) -> None:
    var_root = resolve_var_root(config_path).resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(var_root)
    except ValueError as exc:
        raise CleanError(f"{target} path is outside var: {resolved}") from exc


def _post_preview_stop(url: str, timeout: float = 2.0) -> tuple[bool, str | None]:
    endpoint = url.rstrip("/") + "/api/stop"
    try:
        req = url_request.Request(endpoint, method="POST")
        with url_request.urlopen(req, timeout=timeout) as response:
            if 200 <= response.status < 300:
                return True, None
            return False, f"Preview stop failed with HTTP {response.status}"
    except (url_error.URLError, ValueError) as exc:
        return False, str(exc)


def _preview_api_reachable(url: str, timeout: float = 1.0) -> tuple[bool, str | None]:
    endpoint = url.rstrip("/") + "/api/state"
    try:
        with url_request.urlopen(endpoint, timeout=timeout) as response:
            if 200 <= response.status < 300:
                return True, None
            return False, f"Preview state probe failed with HTTP {response.status}"
    except (url_error.URLError, ValueError) as exc:
        return False, str(exc)


def _port_is_open(host: str, port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_port_close(host: str, port: int, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _port_is_open(host, port, timeout=0.2):
            return True
        time.sleep(0.1)
    return False


def _preview_pid_is_live(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _preview_session_conflict(session: PreviewSession) -> tuple[bool, str]:
    api_ok, api_error = _preview_api_reachable(session.url)
    if api_ok:
        detail = f"Preview session already running at {session.url}"
        if session.project_id:
            detail += f" (project={session.project_id})"
        return True, detail
    port_open = _port_is_open(session.host, session.port)
    if _preview_pid_is_live(session.pid) and port_open:
        return True, (
            "Preview session file points to a running process, but the preview API "
            f"is not responding yet ({api_error or 'unknown error'})."
        )
    if port_open:
        return True, (
            "Preview port is still in use even though the recorded preview process is "
            f"not live ({session.host}:{session.port})."
        )
    return False, api_error or "Recorded preview session is stale"


def _terminate_preview_process(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        typer.echo(f"ERROR: Failed to terminate preview process: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _resolve_sot_root(sot_path: Path | None, config: Path) -> Path:
    try:
        resolved = resolve_sot_path(sot_path, config)
        return resolve_versioned_root(resolved)
    except (FileNotFoundError, ValueError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _resolve_workspace_root(config: Path = Path("config/workbench.yaml")) -> Path:
    try:
        return resolve_project_root(resolve_config_path(config))
    except FileNotFoundError:
        return Path.cwd()


def _print_quickstart_summary(
    result: BuildResult,
    sample_sot: Path,
    *,
    use_configured_sot: bool,
) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("sample_sot", sample_sot),
        ("variant", result.variant.id),
        ("outputs_dir", result.dist_dir),
        ("run_dir", result.run_dir),
        ("manifest_dist", result.dist_dir / "manifest.json"),
        ("manifest_run", result.run_dir / "manifest.json"),
    ]
    if result.theme_id:
        rows.append(("theme", result.theme_id))
    if result.style_preset:
        rows.append(("style_preset", result.style_preset))
    if use_configured_sot:
        rows.append(("next_step", shell_command(f"preview --variant {result.variant.id}")))
    else:
        rows.append(
            (
                "next_step",
                shell_command(f"preview --sot-path {sample_sot} --variant {result.variant.id}"),
            )
        )
    for fmt in result.formats:
        rows.append((f"output_{fmt}", output_path(result.dist_dir, result.variant, fmt)))
    print_summary("quickstart", rows)


def _print_tailor_summary(paths: DraftPaths, output_dir: Path, base_variant: str) -> None:
    print_summary(
        "tailor",
        [
            ("draft_dir", output_dir),
            ("base_variant", base_variant),
            ("variant", paths.variant_path),
            ("patch", paths.patch_path),
            ("job", paths.job_path),
            ("prompt", paths.prompt_path),
        ],
    )


def _print_project_new_summary(
    *,
    project_dir: Path,
    variant_id: str,
    job_source: str,
) -> None:
    print_summary(
        "project.new",
        [
            ("project_dir", project_dir),
            ("proposal_variant", variant_id),
            ("job_source", job_source),
            ("next_step", shell_command(f"project show {project_dir.name}")),
            ("preview_step", shell_command(f"preview --project {project_dir.name}")),
        ],
    )


def _project_summary_payload(
    *,
    command: str,
    project_id: str,
    project_dir: Path,
    base_variant: str,
    job_source: str,
    config_path: Path,
    proposal_variant_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "command": command,
        "project": {
            "project_id": project_id,
            "project_dir": str(project_dir),
            "base_variant": base_variant,
            "job_source": job_source,
        },
        "commands": project_commands(
            project_id,
            config_path=config_path,
            variant_id=proposal_variant_id or base_variant,
        ),
    }
    if proposal_variant_id is not None:
        payload["proposal"] = {"variant_id": proposal_variant_id}
    return payload


def _print_project_guide_summary(summary: dict[str, Any]) -> None:
    evidence = summary["proposal_plan"].get("job_evidence", [])
    evidence_summary = ", ".join(
        f"{item['keyword']}({item['mentions']})" for item in evidence if isinstance(item, dict)
    )
    rows = [
        ("project_dir", summary["project"]["project_dir"]),
        ("base_variant", summary["project"]["base_variant"]),
        ("proposal_variant", summary["proposal"]["variant_id"]),
        ("job_source", summary["project"]["job_source"]),
        ("job_keywords", ", ".join(summary["job"]["keywords"]) or "none"),
        ("job_keywords_in_sot", ", ".join(summary["job"]["keywords_in_sot"]) or "none"),
        ("job_keywords_missing", ", ".join(summary["job"]["keywords_missing"]) or "none"),
        ("recommended_variant", summary["proposal_plan"]["selected_variant"] or "none"),
        ("selection_mode", summary["proposal_plan"]["selection_mode"]),
        ("recommendation_status", summary["proposal_plan"]["status"]),
        ("recommendation_summary", summary["proposal_plan"]["summary"]),
        ("job_evidence", evidence_summary or "none"),
        ("sot_tags_top", summary["sot"]["tags_summary"]),
        ("recommendations", recommendations_summary_line(summary["recommendations"])),
        (
            "next_step",
            shell_command(f"project show {summary['project']['project_id']}"),
        ),
        (
            "preview_step",
            shell_command(f"preview --project {summary['project']['project_id']}"),
        ),
    ]
    print_summary("project.guide", rows)


def _print_project_apply_summary(project_dir: Path, sot_path: Path) -> None:
    print_summary(
        "project.apply",
        [
            ("project_dir", project_dir),
            ("sot_path", sot_path),
        ],
    )


def _print_project_show_summary(summary: dict[str, Any]) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("project_dir", summary["project"]["project_dir"]),
        ("created_at", summary["project"]["created_at"]),
        ("base_variant", summary["project"]["base_variant"]),
        ("proposal_variant", summary["proposal"]["variant_id"]),
        ("proposal_document_type", summary["proposal"]["document_type"]),
        ("patch_status", summary["patch"]["status"]),
        ("patch_ops", ",".join(summary["patch"]["operations"]) or "none"),
        ("job_source", summary["job"]["source"]),
        ("next_step", summary["commands"]["preview"]),
        ("build_step", summary["commands"]["build"]),
        ("review_status", summary["review"]["status"]),
        ("review_step", summary["review"]["next_command"]),
        ("apply_step", summary["commands"]["apply"]),
        ("keep_step", summary["commands"]["keep"]),
        ("discard_step", summary["commands"]["discard"]),
    ]
    rows.extend(_proposal_plan_summary_rows(summary.get("proposal_plan")))
    if summary["patch"]["render_warning"]:
        rows.append(("patch_note", summary["patch"]["render_warning"]))
    if summary["review"]["run_id"]:
        rows.append(("review_run", summary["review"]["run_id"]))
    if "proposal_plan_error" in summary:
        rows.append(("proposal_plan_error", summary["proposal_plan_error"]))
    print_summary("project.show", rows)


def _print_project_patch_summary(summary: dict[str, Any]) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("project_dir", summary["project"]["project_dir"]),
        ("sot_path", summary["project"]["sot_path"]),
        ("patch_path", summary["patch"]["path"]),
        ("patch_status", summary["patch"]["status"]),
        ("operation", summary["operation"]["op"]),
        ("target", summary["operation"]["target"]),
        ("next_step", summary["commands"]["show"]),
        ("preview_step", summary["commands"]["preview"]),
        ("apply_step", summary["commands"]["apply"]),
    ]
    print_summary("project.patch", rows)


def _print_apply_summary(
    draft_dir: Path,
    patch_path: Path,
    status: str,
    reason: str,
    sot_path: Path,
) -> None:
    print_summary(
        "apply",
        [
            ("draft_dir", draft_dir),
            ("patch", patch_path),
            ("status", status),
            ("reason", reason),
            ("sot_path", sot_path),
        ],
    )


def _reviewpack_error_hint(
    *,
    message: str,
    project: str | None,
    run: str | None,
    variant_id: str | None,
) -> str:
    if message.startswith("Run does not belong to project:"):
        project_label = project or "<project-id>"
        selector_hint = shell_command(f"reviewpack --project {project_label}")
        return (
            f"HINT: the selected run does not belong to project {project_label!r}. "
            f"Use `{selector_hint}` to package that project's latest run, pass a "
            "matching `--run projects/<project-id>/<run-id>`, or drop `--project` "
            "if you intended to package the selected run directly."
        )
    if message.startswith("Review pack already exists:"):
        if run is not None:
            force_hint = shell_command(f"reviewpack --run {run} --force")
        elif project is not None:
            force_hint = shell_command(f"reviewpack --project {project} --force")
        else:
            force_hint = shell_command(f"reviewpack --variant {variant_id or '<variant>'} --force")
        return f"HINT: use `{force_hint}` to replace the existing review pack explicitly."

    build_hint = (
        f"build --project {project!r} --format md,pdf,docx"
        if project is not None
        else f"build --variant {variant_id or '<variant>'} --format md,pdf,docx"
    )
    return (
        "HINT: build the target variant with review artifacts first, for example "
        f"`{shell_command(build_hint)}`, "
        f"inspect `{shell_command('workflow --id review.import')}`, "
        "pass `--run <run-id>` to package a specific build deterministically, "
        "or use `--force` to replace an existing review pack."
    )


@app.command(help="Validate the configured SoT and fail fast on schema or file errors.")
def validate(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        resolved = resolve_sot_path(sot_path, config)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    errors = _validate_sot(resolved)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)
    _print_validate_summary(resolved)


@app.command(help="Check local toolchain dependencies and workspace prerequisites.")
def doctor(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        checks = run_doctor(config)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    rows: list[tuple[str, str | Path]] = []
    missing: list[str] = []
    for check in checks:
        status = "ok" if check.ok else "missing"
        detail = status
        if check.version:
            detail = f"{status} ({check.version})"
        elif check.message:
            detail = f"{status} ({check.message})"
        rows.append((check.name, detail))
        if not check.ok:
            missing.append(check.name)

    _print_doctor_summary(rows)
    if missing:
        typer.echo(
            f"ERROR: Missing dependencies: {', '.join(missing)}",
            err=True,
        )
        raise typer.Exit(code=1)


@app.command(help="Summarize the current SoT, variants, runs, projects, and reviews.")
def status(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        summary = inspect_status(config=config, sot_path=sot_path)
    except StatusInspectionError as exc:
        for error in exc.errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1) from exc
    except (OSError, ValueError, RunError, VariantLifecycleError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"command": "status", **summary}, indent=2, sort_keys=True))
        return

    _print_status_summary(summary)


@app.command(
    help=(
        "Scan workspace state and recommend the next 1-3 workflows. "
        "Use --json --compact for bootstrap, logs, and agent handoff."
    )
)
def bootstrap(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        summary = inspect_workspace(
            sot_path=sot_path,
            strict=False,
            config=config,
            compact=True,
        )
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if get_output_mode() == OutputMode.JSON:
        payload = _compact_context_payload(summary)
        typer.echo(json.dumps({"command": "bootstrap", **payload}, indent=2, sort_keys=True))
        return

    _print_bootstrap_summary(summary)


@app.command(
    help=(
        "Scan workspace state and recommend the next 1-3 workflows. "
        "Use --json --compact for bootstrap, logs, and agent handoff."
    )
)
def context(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Fail fast when required inputs are missing",
        ),
    ] = False,
    compact: Annotated[
        bool,
        typer.Option(
            "--compact",
            help="Use summary-only JSON output for bootstrap, logs, and agent handoff",
        ),
    ] = False,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    if compact and get_output_mode() != OutputMode.JSON:
        typer.echo("ERROR: --compact requires --json", err=True)
        raise typer.Exit(code=2)
    try:
        summary = inspect_workspace(
            sot_path=sot_path,
            strict=strict,
            config=config,
            compact=compact,
        )
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if get_output_mode() == OutputMode.JSON:
        payload = _compact_context_payload(summary) if compact else summary
        typer.echo(json.dumps({"command": "context", **payload}, indent=2, sort_keys=True))
        return

    _print_context_summary(summary)


@app.command(
    help=(
        "Inspect workflow recipes from context. Use --json --compact when you want "
        "recipe-focused retrieval instead of the full workspace summary."
    )
)
def workflow(
    recipe_id: Annotated[
        str | None,
        typer.Option(
            "--id",
            help="Show only one workflow recipe by id",
        ),
    ] = None,
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
    compact: Annotated[
        bool,
        typer.Option(
            "--compact",
            help="Use summary-only JSON output for recipe retrieval and agent handoff",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    if compact and get_output_mode() != OutputMode.JSON:
        typer.echo("ERROR: --compact requires --json", err=True)
        raise typer.Exit(code=2)
    try:
        summary = inspect_workspace(
            sot_path=sot_path,
            strict=False,
            config=config,
            compact=compact,
        )
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    recipes = summary["recipes"]
    if recipe_id is not None:
        recipes = [recipe for recipe in recipes if recipe["id"] == recipe_id]
        if not recipes:
            typer.echo(f"ERROR: Unknown workflow id: {recipe_id}", err=True)
            raise typer.Exit(code=1)

    payload = {
        "config": summary["config"],
        "sot": summary["sot"],
        "recipes": recipes,
        "issues": summary["issues"],
    }

    if get_output_mode() == OutputMode.JSON:
        if compact:
            payload = _compact_workflow_payload(summary, recipes)
        typer.echo(json.dumps({"command": "workflow", **payload}, indent=2, sort_keys=True))
        return

    _print_workflow_summary(
        recipes=recipes,
        sot_status=summary["sot"]["status"],
        issues=summary["issues"],
        selected_recipe=recipe_id,
    )


@app.command(
    help=(
        "Create or repair local workspace scaffolding, default config, and sample/private "
        "SoT layout."
    )
)
def init(
    workspace: Annotated[
        Path | None,
        typer.Option(
            "--workspace",
            help="Workspace root to initialize when running outside the target directory",
        ),
    ] = None,
    sample_default: Annotated[
        bool,
        typer.Option(
            "--sample-default",
            help="Use ./sot.sample as the configured default SoT instead of copying it to local/sot",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    root = workspace.resolve() if workspace is not None else _resolve_workspace_root()
    try:
        result = init_project(root, sample_default=sample_default)
    except ScaffoldError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    statuses = result.statuses
    summary = {
        "root": result.root,
        "sot_path": result.sot_path,
        "sot_profile": statuses.get("sot_profile", "local-copy"),
        "sot_status": statuses.get("sot", "unknown"),
        "workbench_config": result.config_path,
        "workbench_status": statuses.get("workbench_config", "unknown"),
        "base_variant": result.variant_path,
        "base_variant_status": statuses.get("base_variant", "unknown"),
        "publish_config": result.config_path.parent / "publish.yaml",
        "publish_status": statuses.get("publish_config", "unknown"),
        "themes_path": result.root / "build" / "themes",
        "themes_status": statuses.get("themes", "unknown"),
        "registry_path": result.registry_path,
        "registry_status": statuses.get("registry", "unknown"),
        "pre_commit_hooks": statuses.get("pre_commit_hooks", "unknown"),
    }
    if statuses.get("pre_commit_hooks_detail"):
        summary["pre_commit_hooks_detail"] = statuses["pre_commit_hooks_detail"]
    _print_init_summary(summary)


@app.command(
    help=(
        "Initialize the sample workspace and build the base variant once. "
        "Use build/preview directly when you want explicit control."
    )
)
def quickstart(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    sample_default: Annotated[
        bool,
        typer.Option(
            "--sample-default",
            help="Use ./sot.sample as the configured default SoT after scaffold setup",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    workspace_root = _resolve_workspace_root(config)
    resolved_config = config if config.is_absolute() else workspace_root / config
    try:
        init_project(workspace_root, sample_default=sample_default)
    except ScaffoldError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    template_root = resolve_template_root()
    sample_sot = template_root / "sot.sample"
    use_configured_sot = False
    try:
        configured_sot = resolve_sot_path(None, resolved_config)
    except (FileNotFoundError, ValueError):
        configured_sot = None
    if (
        configured_sot is not None
        and configured_sot.exists()
        and configured_sot.name == "sot.sample"
    ):
        sample_sot = configured_sot
        use_configured_sot = True
    if not sample_sot.exists():
        typer.echo(f"ERROR: Sample SoT not found: {sample_sot}", err=True)
        raise typer.Exit(code=1)

    errors = _validate_sot(sample_sot)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)

    try:
        result = build_documents(
            sot_path=sample_sot,
            config_path=resolved_config,
            variant_id="base",
            formats=["md", "pdf", "docx"],
        )
    except (ValueError, RenderError, ThemeError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_quickstart_summary(result, sample_sot, use_configured_sot=use_configured_sot)


@theme_app.command("list")
def theme_list(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        themes_dir = resolve_themes_dir(config)
        default_theme = resolve_default_theme(config)
        themes = list_themes(themes_dir)
    except (ValueError, ThemeError, FileNotFoundError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    theme_ids = [theme.id for theme in themes]
    _print_theme_list_summary(theme_ids, default_theme)


@theme_app.command("info")
def theme_info(
    theme: Annotated[
        str,
        typer.Argument(help="Theme id"),
    ],
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        themes_dir = resolve_themes_dir(config)
        resolved = resolve_theme(themes_dir, theme)
    except (ValueError, ThemeError, FileNotFoundError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    routes = list(resolved.routes.keys())
    presets = list_theme_presets(resolved)
    _print_theme_info_summary(resolved.id, resolved.description, routes, presets)


@variant_app.command(
    "promote",
    help="Legacy draft promotion path. Prefer `variant keep` for lifecycle-aware promotion.",
)
def variant_promote(
    draft: Annotated[
        Path,
        typer.Option(
            "--draft",
            help="Draft directory containing variant.yaml",
        ),
    ],
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    variant_id: Annotated[
        str | None,
        typer.Option(
            "--id",
            help="Override the promoted variant id",
        ),
    ] = None,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        result = promote_variant(
            draft_dir=draft,
            config_path=config,
            variant_id=variant_id,
        )
    except (PromoteError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_variant_promote_summary(result.variant_id, result.variant_path, result.status)


@variant_app.command("list", help="Show configured variants alongside lifecycle inbox entries.")
def variant_list(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    config_path = resolve_config_path(config)
    try:
        variants = load_variants_from_config(config_path)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    inbox_entries = list_variant_inbox(config_path)
    inbox_payload = [inbox_entry_payload(entry, config_path) for entry in inbox_entries]
    ttl_days = resolve_variant_ttl_days(config_path)

    payload = {
        "command": "variant.list",
        "variants": variants,
        "ttl_days": ttl_days,
        "inbox": inbox_payload,
        "inbox_count": len(inbox_payload),
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    rows = [
        ("count", str(len(variants))),
        ("variants", variants_summary_line(variants) or "none"),
        ("inbox", inbox_summary_line(inbox_payload)),
        ("ttl_days", str(ttl_days)),
    ]
    print_summary("variant.list", rows)


@variant_app.command(
    "inbox",
    help="List pending draft/project proposals and flag entries that are expired pending garbage collection.",
)
def variant_inbox(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    config_path = resolve_config_path(config)
    try:
        entries = list_variant_inbox(config_path)
    except (VariantLifecycleError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_variant_inbox(entries, config_path)


@variant_app.command(
    "keep", help="Promote an ephemeral draft or project proposal into config/variants."
)
def variant_keep(
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Path to variant.yaml to promote",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path whose proposal variant should be promoted",
        ),
    ] = None,
    variant_id: Annotated[
        str | None,
        typer.Option(
            "--id",
            help="Override the promoted variant id",
        ),
    ] = None,
    label: Annotated[
        str | None,
        typer.Option(
            "--label",
            help="Checkpoint label for the kept variant",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    config_path = resolve_config_path(config)
    if (path is None) == (project is None):
        typer.echo("ERROR: Provide exactly one of --path or --project", err=True)
        raise typer.Exit(code=2)
    try:
        resolved_path = _resolve_variant_lifecycle_path(
            path=path,
            project=project,
            config_path=config_path,
        )
    except (ProjectError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    try:
        result = keep_variant(
            variant_path=resolved_path,
            config_path=config_path,
            variant_id=variant_id,
            label=label,
        )
    except (VariantLifecycleError, FileNotFoundError, ValueError, ProjectError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_variant_keep_summary(result.variant_id, result.variant_path, result.status)


@variant_app.command(
    "discard", help="Discard an ephemeral draft or project proposal after explicit approval."
)
def variant_discard(
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Path to variant.yaml to discard",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path whose proposal variant should be discarded",
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of the draft/proposal artifacts",
        ),
    ] = False,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    config_path = resolve_config_path(config)
    if (path is None) == (project is None):
        typer.echo("ERROR: Provide exactly one of --path or --project", err=True)
        raise typer.Exit(code=2)
    try:
        resolved_path = _resolve_variant_lifecycle_path(
            path=path,
            project=project,
            config_path=config_path,
        )
    except (ProjectError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    try:
        result = discard_variant(
            variant_path=resolved_path,
            config_path=config_path,
            confirm=yes,
        )
    except (VariantLifecycleError, FileNotFoundError, ValueError, ProjectError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_variant_discard_summary(result.variant_path, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


@variant_app.command("gc", help="Preview or remove expired draft/project proposal artifacts.")
def variant_gc(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of expired draft/proposal artifacts",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        summary = gc_variants(config_path=config, confirm=yes)
    except (VariantLifecycleError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_variant_gc_summary(summary)
    if not yes and summary.status == "dry_run":
        raise typer.Exit(code=2)


@runs_app.command("gc")
def runs_gc(
    keep_latest: Annotated[
        int,
        typer.Option(
            "--keep-latest",
            min=0,
            help="Number of most recent runs to keep per project and variant",
        ),
    ] = 1,
    keep: Annotated[
        list[str] | None,
        typer.Option(
            "--keep",
            help="Run id to keep (repeatable)",
        ),
    ] = None,
    include_invalid: Annotated[
        bool,
        typer.Option(
            "--include-invalid",
            help="Delete invalid run directories as part of GC",
        ),
    ] = False,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of selected run artifacts",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        config_path = resolve_config_path(config)
        runs_root = resolve_runs_path(config_path)
        _require_var_path("runs", runs_root, config_path)
        summary = gc_runs(
            config_path=config_path,
            keep_latest=keep_latest,
            keep=keep or [],
            include_invalid=include_invalid,
            confirm=yes,
        )
    except (RunError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    payload = {
        "command": "runs.gc",
        "keep_latest": keep_latest,
        "keep": keep or [],
        "include_invalid": include_invalid,
        "status": summary.status,
        "removed": summary.removed,
        "candidates": [_run_gc_candidate_payload(candidate) for candidate in summary.candidates],
        "kept": [run_payload(run) for run in summary.kept],
        "invalid": [str(path) for path in summary.invalid],
        "invalid_candidates": [str(path) for path in summary.invalid_candidates],
        "keep_reasons": summary.keep_reasons,
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_runs_gc_summary(summary, keep_latest, include_invalid)

    if not yes and summary.status == "dry_run":
        raise typer.Exit(code=2)


@clean_app.command("runs")
def clean_runs(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of all run artifacts",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        config_path = resolve_config_path(config)
        path = resolve_runs_path(config_path)
        _require_var_path("runs", path, config_path)
        result = clean_path(target="runs", path=path, confirm=yes)
    except (CleanError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_clean_summary(result.target, result.path, result.removed, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


@clean_app.command("dist")
def clean_dist(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of all dist artifacts",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        config_path = resolve_config_path(config)
        path = resolve_dist_path(config_path)
        _require_var_path("dist", path, config_path)
        result = clean_path(target="dist", path=path, confirm=yes)
    except (CleanError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_clean_summary(result.target, result.path, result.removed, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


@clean_app.command("drafts")
def clean_drafts(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of all draft artifacts",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        config_path = resolve_config_path(config)
        path = resolve_drafts_path(config_path)
        _require_var_path("drafts", path, config_path)
        result = clean_path(target="drafts", path=path, confirm=yes)
    except (CleanError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_clean_summary(result.target, result.path, result.removed, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


@clean_app.command("registry")
def clean_registry(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of all registry artifacts",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        config_path = resolve_config_path(config)
        path = resolve_registry_path(config_path)
        _require_var_path("registry", path, config_path)
        result = clean_path(target="registry", path=path, confirm=yes)
    except (CleanError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_clean_summary(result.target, result.path, result.removed, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


@clean_app.command("reviews")
def clean_reviews(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of all review artifacts",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        config_path = resolve_config_path(config)
        path = resolve_reviews_path(config_path)
        _require_var_path("reviews", path, config_path)
        result = clean_path(target="reviews", path=path, confirm=yes)
    except (CleanError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_clean_summary(result.target, result.path, result.removed, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


@clean_app.command("projects")
def clean_projects(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Confirm deletion of all project artifacts",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        config_path = resolve_config_path(config)
        path = resolve_projects_path(config_path)
        _require_var_path("projects", path, config_path)
        result = clean_path(target="projects", path=path, confirm=yes)
    except (CleanError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_clean_summary(result.target, result.path, result.removed, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


@sot_app.command("list")
def sot_list(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the SoT version pack root",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    root = _resolve_sot_root(sot_path, config)
    try:
        state = list_versions(root)
    except (SotPackError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    print_summary(
        "sot.list",
        [
            ("root", state.root),
            ("active", state.active),
            ("versions", ", ".join(state.versions)),
        ],
    )


@sot_app.command("new")
def sot_new(
    name: Annotated[
        str,
        typer.Argument(help="Name for the new SoT version"),
    ],
    from_version: Annotated[
        str | None,
        typer.Option(
            "--from",
            help="Base SoT version to copy from",
        ),
    ] = None,
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the SoT version pack root",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    root = _resolve_sot_root(sot_path, config)
    try:
        state = list_versions(root)
        base = from_version or state.active
        target = create_version(root, name, base)
    except (SotPackError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    print_summary(
        "sot.new",
        [
            ("name", name),
            ("from", base),
            ("path", target),
        ],
    )


@sot_app.command("activate")
def sot_activate(
    name: Annotated[
        str,
        typer.Argument(help="SoT version to activate"),
    ],
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the SoT version pack root",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    root = _resolve_sot_root(sot_path, config)
    try:
        activate_version(root, name)
    except (SotPackError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    print_summary(
        "sot.activate",
        [
            ("root", root),
            ("active", name),
        ],
    )


@sot_app.command("diff")
def sot_diff(
    left: Annotated[
        str,
        typer.Argument(help="Left-hand SoT version"),
    ],
    right: Annotated[
        str,
        typer.Argument(help="Right-hand SoT version"),
    ],
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the SoT version pack root",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    root = _resolve_sot_root(sot_path, config)
    try:
        diff_text = diff_versions(root, left, right)
    except (SotPackError, SotVersionError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if diff_text:
        typer.echo(diff_text)
        return
    typer.echo("No differences found.")


@job_app.command("add")
def job_add(
    url: Annotated[
        str,
        typer.Option(
            "--url",
            help="URL to ingest as a context source",
        ),
    ],
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        entry = add_url_context(url, config)
    except (FileNotFoundError, ValueError, RegistryError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    summary = {
        "context_id": entry.context_id,
        "context_path": entry.path,
        "source": entry.source_path,
        "extracted": entry.extracted_path,
        "signals": entry.signals_path,
        "strategy": entry.strategy_path,
    }
    _print_job_add_summary(summary)


@project_app.command(
    "new",
    help=(
        "Create a project workspace directly from a chosen base variant, with a "
        "project-local proposal variant and patch scaffold. Use `project guide` "
        "if you want ranked recommendations first. `--open` cannot be combined "
        "with `--json`."
    ),
)
def project_new(
    job_url: Annotated[
        str | None,
        typer.Option(
            "--job-url",
            help="Job URL to ingest",
        ),
    ] = None,
    job_file: Annotated[
        Path | None,
        typer.Option(
            "--job-file",
            help="Job description file",
        ),
    ] = None,
    slug: Annotated[
        str | None,
        typer.Option(
            "--slug",
            help="Project id override",
        ),
    ] = None,
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Base variant id",
        ),
    ] = None,
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    store_raw: Annotated[
        bool,
        typer.Option(
            "--store-raw",
            help="Store raw HTML when ingesting a URL",
        ),
    ] = False,
    open_after: Annotated[
        bool,
        typer.Option(
            "--open",
            help="Open preview after creating the project",
        ),
    ] = False,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    if bool(job_url) == bool(job_file):
        typer.echo("ERROR: Provide exactly one of --job-url or --job-file", err=True)
        raise typer.Exit(code=2)
    if json_output and open_after:
        typer.echo("ERROR: --open cannot be combined with --json", err=True)
        raise typer.Exit(code=2)

    config_path = resolve_config_path(config)
    base_variant = variant or resolve_default_variant(config_path)

    try:
        resolved_sot = resolve_sot_path(sot_path, config_path)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        if job_url:
            result = create_project_from_url(
                url=job_url,
                slug=slug,
                base_variant_id=base_variant,
                config_path=config_path,
                sot_path=resolved_sot,
                store_raw=store_raw,
            )
            job_source = job_url
        else:
            result = create_project_from_file(
                job_path=job_file or Path(),
                slug=slug,
                base_variant_id=base_variant,
                config_path=config_path,
                sot_path=resolved_sot,
                store_raw=store_raw,
            )
            job_source = str(job_file)
    except (ProjectError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    summary = _project_summary_payload(
        command="project.new",
        project_id=result.project_dir.name,
        project_dir=result.project_dir,
        base_variant=base_variant,
        job_source=job_source,
        config_path=config_path,
        proposal_variant_id=load_variant(result.variant_path).id,
    )

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(summary, indent=2, sort_keys=True))
    else:
        _print_project_new_summary(
            project_dir=result.project_dir,
            variant_id=load_variant(result.variant_path).id,
            job_source=job_source,
        )

    if open_after:
        dev_serve(
            sot_path=resolved_sot,
            config=config_path,
            theme=None,
            style_preset=None,
            plain=plain,
            json_output=json_output,
            project=result.project_dir.name,
        )


@project_app.command(
    "guide",
    help=(
        "Ingest a job posting, rank candidate variants, and scaffold a "
        "project-local proposal workspace from the selected base variant. "
        "This produces recommendations and editable project artifacts; it does "
        "not rewrite the SoT. `--open` cannot be combined with `--json`."
    ),
)
def project_guide(
    job_url: Annotated[
        str | None,
        typer.Option(
            "--job-url",
            help="Job URL to ingest",
        ),
    ] = None,
    job_file: Annotated[
        Path | None,
        typer.Option(
            "--job-file",
            help="Job description file",
        ),
    ] = None,
    slug: Annotated[
        str | None,
        typer.Option(
            "--slug",
            help="Project id override",
        ),
    ] = None,
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Base variant id",
        ),
    ] = None,
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    store_raw: Annotated[
        bool,
        typer.Option(
            "--store-raw",
            help="Store raw HTML when ingesting a URL",
        ),
    ] = False,
    open_after: Annotated[
        bool,
        typer.Option(
            "--open",
            help="Open preview after creating the project",
        ),
    ] = False,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    if bool(job_url) == bool(job_file):
        typer.echo("ERROR: Provide exactly one of --job-url or --job-file", err=True)
        raise typer.Exit(code=2)
    if json_output and open_after:
        typer.echo("ERROR: --open cannot be combined with --json", err=True)
        raise typer.Exit(code=2)

    config_path = resolve_config_path(config)
    try:
        configured_default_variant = resolve_default_variant(config_path)
        requested_variant = variant or configured_default_variant
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        resolved_sot = resolve_sot_path(sot_path, config_path)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    errors = _validate_sot(resolved_sot)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)
    try:
        sot_payload = load_sot(resolved_sot)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    tags = extract_tags(sot_payload)
    counts = tag_counts(tags)
    tags_top = top_tags(counts)
    tags_summary = tags_summary_line(tags_top)

    try:
        if job_url:
            project_paths = create_project_from_url(
                url=job_url,
                slug=slug,
                base_variant_id=requested_variant,
                config_path=config_path,
                sot_path=resolved_sot,
                store_raw=store_raw,
            )
            job_source = job_url
        else:
            project_paths = create_project_from_file(
                job_path=job_file or Path(),
                slug=slug,
                base_variant_id=requested_variant,
                config_path=config_path,
                sot_path=resolved_sot,
                store_raw=store_raw,
            )
            job_source = str(job_file)
    except (ProjectError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        signals = load_job_signals(project_paths.signals_path)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    raw_keywords: list[str] = []
    keywords_value = signals.get("keywords")
    if isinstance(keywords_value, list):
        raw_keywords = [item for item in keywords_value if isinstance(item, str)]
    job_keywords = normalize_keywords(raw_keywords)
    keyword_overlap = job_keyword_overlap(job_keywords, counts)
    signal_counts = job_signal_counts(signals, job_keywords)
    job_text = project_paths.extracted_path.read_text()
    job_evidence = build_job_evidence(
        job_text,
        signals=signals,
        job_keywords=job_keywords,
    )

    try:
        variants = load_variants_from_config(config_path)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    recommendations = recommend_variants(
        variants,
        job_keywords,
        counts,
        configured_default_variant,
        signal_counts,
    )
    applied_variant = requested_variant
    selection_mode = "explicit" if variant else "requested"
    selected_recommendation = recommendations[0] if recommendations else None
    if (
        variant is None
        and selected_recommendation is not None
        and selected_recommendation["eligible"]
    ):
        recommended_variant = selected_recommendation["variant_id"]
        if recommended_variant != requested_variant:
            try:
                retarget_project_variant(
                    project_dir=project_paths.project_dir,
                    base_variant_id=recommended_variant,
                    config_path=config_path,
                )
            except Exception as exc:
                try:
                    discard_project_workspace(
                        project_dir=project_paths.project_dir,
                        config_path=config_path,
                    )
                except Exception as rollback_exc:
                    typer.echo(f"ERROR: {exc}", err=True)
                    typer.echo(
                        "ERROR: Failed to roll back the project workspace after guide retargeting failed: "
                        f"{rollback_exc}",
                        err=True,
                    )
                    raise typer.Exit(code=1) from exc
                typer.echo(f"ERROR: {exc}", err=True)
                raise typer.Exit(code=1) from exc
        applied_variant = recommended_variant
        selection_mode = "recommended"
    proposal_plan = build_proposal_plan(
        project_id=project_paths.project_dir.name,
        project_dir=project_paths.project_dir,
        job_keywords=job_keywords,
        keyword_overlap=keyword_overlap,
        recommendations=recommendations,
        job_evidence=job_evidence,
        requested_variant=requested_variant,
        applied_variant=applied_variant,
        selection_mode=selection_mode,
    )
    proposal_plan_path = Path(proposal_plan["path"])
    proposal_plan_path.write_text(json.dumps(proposal_plan, indent=2, sort_keys=True) + "\n")

    summary = {
        **_project_summary_payload(
            command="project.guide",
            project_id=project_paths.project_dir.name,
            project_dir=project_paths.project_dir,
            base_variant=applied_variant,
            job_source=job_source,
            config_path=config_path,
            proposal_variant_id=load_variant(project_paths.variant_path).id,
        ),
        "job": {
            "keywords": job_keywords,
            "keywords_in_sot": keyword_overlap["matched"],
            "keywords_missing": keyword_overlap["missing"],
            "evidence": job_evidence,
        },
        "sot": {
            "path": str(resolved_sot),
            "tags_top": tags_top,
            "tags_summary": tags_summary,
        },
        "variants": {
            "config": variants,
            "count": len(variants),
            "default": configured_default_variant,
        },
        "recommendations": recommendations,
        "proposal_plan": proposal_plan,
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(summary, indent=2, sort_keys=True))
    else:
        _print_project_guide_summary(summary)

    if open_after:
        dev_serve(
            sot_path=resolved_sot,
            config=config_path,
            theme=None,
            style_preset=None,
            plain=plain,
            json_output=json_output,
            project=project_paths.project_dir.name,
        )


@project_app.command(
    "show",
    help=(
        "Inspect a project proposal, patch status, latest project run, review readiness, "
        "and ready-to-run next commands without mutating the SoT."
    ),
)
def project_show(
    project: Annotated[
        str,
        typer.Argument(help="Project id or path"),
    ],
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    config_path = resolve_config_path(config)
    project_dir = resolve_project_dir(project, config_path)
    try:
        details = load_project_details(project_dir)
    except ProjectError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    review = project_review_payload(details.spec.project_id, config_path)
    commands = project_commands(
        details.spec.project_id,
        config_path=config_path,
        variant_id=details.proposal_variant_id,
        review_run_id=review["run_id"] if review["review_ready"] else None,
    )
    review["next_command"] = commands.get("reviewpack", commands["build"])
    render_warning = project_patch_render_warning(
        proposal_document_type=details.proposal_document_type,
        patch_operations=details.patch_operations,
    )
    patch_status = project_patch_status(
        patch_format=details.patch_format,
        patch_is_empty=details.patch_is_empty,
        patch_line_count=details.patch_line_count,
    )
    proposal_plan_path = details.signals_path.parent / "proposal-plan.json"
    proposal_plan, proposal_plan_error = load_optional_json(proposal_plan_path)
    summary = {
        "project": {
            "project_id": details.spec.project_id,
            "project_dir": str(details.spec.project_dir),
            "created_at": details.created_at,
            "base_variant": details.spec.base_variant_id,
            "sot_path": str(details.spec.sot_path),
        },
        "proposal": {
            "variant_id": details.proposal_variant_id,
            "variant_path": str(details.spec.variant_path),
            "document_type": details.proposal_document_type,
        },
        "job": {
            "source_type": details.job_source_type,
            "source": details.job_source_value,
            "extracted_path": str(details.extracted_path),
            "raw_path": str(details.raw_path) if details.raw_path is not None else None,
        },
        "signals": {
            "path": str(details.signals_path),
        },
        "patch": {
            "path": str(details.spec.patch_path),
            "format": details.patch_format,
            "is_empty": details.patch_is_empty,
            "line_count": details.patch_line_count,
            "operations": list(details.patch_operations),
            "render_warning": render_warning,
            "status": patch_status,
        },
        "review": review,
        "commands": commands,
    }
    if proposal_plan is not None:
        summary["proposal_plan"] = proposal_plan
    if proposal_plan_error is not None:
        summary["proposal_plan_error"] = proposal_plan_error

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"command": "project.show", **summary}, indent=2, sort_keys=True))
        return

    _print_project_show_summary(summary)


@project_patch_app.command(
    "replace-experience-bullet",
    help=(
        "Append a validated replace-experience-bullet project-op to "
        "proposals/patch.yaml. If --old-text is omitted, the current SoT bullet "
        "text is snapshotted automatically."
    ),
)
def project_patch_replace_experience_bullet(
    project: Annotated[
        str,
        typer.Argument(help="Project id or path"),
    ],
    role_id: Annotated[
        str,
        typer.Option(
            "--role-id",
            help="Stable role id from experience.yaml",
        ),
    ],
    bullet_id: Annotated[
        str,
        typer.Option(
            "--bullet-id",
            help="Stable bullet id from experience.yaml",
        ),
    ],
    new_text: Annotated[
        str,
        typer.Option(
            "--new-text",
            help="Replacement bullet text",
        ),
    ],
    old_text: Annotated[
        str | None,
        typer.Option(
            "--old-text",
            help="Expected existing bullet text; defaults to the current SoT value",
        ),
    ] = None,
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Optional SoT override used for validation and source-text snapshotting",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    config_path = resolve_config_path(config)
    project_dir = resolve_project_dir(project, config_path)
    try:
        spec = load_project(project_dir)
    except ProjectError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    resolved_sot = sot_path.resolve() if sot_path is not None else spec.sot_path.resolve()
    if not resolved_sot.exists():
        typer.echo(f"ERROR: SoT path not found: {resolved_sot}", err=True)
        raise typer.Exit(code=1)

    try:
        patch = append_replace_experience_bullet_operation(
            project_dir=project_dir,
            sot_path=resolved_sot,
            role_id=role_id,
            bullet_id=bullet_id,
            new_text=new_text,
            old_text=old_text,
        )
    except ProjectError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    op_count = len(patch.operations)
    status = f"{op_count} op" if op_count == 1 else f"{op_count} ops"
    followup_sot = resolved_sot if resolved_sot != spec.sot_path.resolve() else None
    commands = project_commands(
        spec.project_id,
        config_path=config_path,
        sot_path=followup_sot,
    )
    summary = {
        "command": "project.patch.replace-experience-bullet",
        "project": {
            "project_id": spec.project_id,
            "project_dir": str(spec.project_dir),
            "sot_path": str(resolved_sot),
        },
        "patch": {
            "path": str(spec.patch_path),
            "format": patch.format,
            "line_count": op_count,
            "status": status,
        },
        "operation": {
            "op": "replace-experience-bullet",
            "target": f"{role_id}:{bullet_id}",
            "role_id": role_id,
            "bullet_id": bullet_id,
            "old_text": patch.operations[-1]["old_text"],
            "new_text": patch.operations[-1]["new_text"],
        },
        "commands": commands,
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(summary, indent=2, sort_keys=True))
        return

    _print_project_patch_summary(summary)


@project_patch_app.command(
    "replace-project-summary",
    help=(
        "Append a validated replace-project-summary project-op to "
        "proposals/patch.yaml. If --old-text is omitted, the current SoT project "
        "summary is snapshotted automatically."
    ),
)
def project_patch_replace_project_summary(
    project: Annotated[
        str,
        typer.Argument(help="Project id or path"),
    ],
    project_id: Annotated[
        str,
        typer.Option(
            "--project-id",
            help="Stable project id from projects.yaml",
        ),
    ],
    new_text: Annotated[
        str,
        typer.Option(
            "--new-text",
            help="Replacement project summary text",
        ),
    ],
    old_text: Annotated[
        str | None,
        typer.Option(
            "--old-text",
            help="Expected existing project summary; defaults to the current SoT value",
        ),
    ] = None,
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Optional SoT override used for validation and source-text snapshotting",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    config_path = resolve_config_path(config)
    project_dir = resolve_project_dir(project, config_path)
    try:
        spec = load_project(project_dir)
    except ProjectError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    resolved_sot = sot_path.resolve() if sot_path is not None else spec.sot_path.resolve()
    if not resolved_sot.exists():
        typer.echo(f"ERROR: SoT path not found: {resolved_sot}", err=True)
        raise typer.Exit(code=1)

    try:
        patch = append_replace_project_summary_operation(
            project_dir=project_dir,
            sot_path=resolved_sot,
            project_id=project_id,
            new_text=new_text,
            old_text=old_text,
        )
    except ProjectError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    op_count = len(patch.operations)
    status = f"{op_count} op" if op_count == 1 else f"{op_count} ops"
    followup_sot = resolved_sot if resolved_sot != spec.sot_path.resolve() else None
    commands = project_commands(
        spec.project_id,
        config_path=config_path,
        sot_path=followup_sot,
    )
    summary = {
        "command": "project.patch.replace-project-summary",
        "project": {
            "project_id": spec.project_id,
            "project_dir": str(spec.project_dir),
            "sot_path": str(resolved_sot),
        },
        "patch": {
            "path": str(spec.patch_path),
            "format": patch.format,
            "line_count": op_count,
            "status": status,
        },
        "operation": {
            "op": "replace-project-summary",
            "target": project_id,
            "project_id": project_id,
            "old_text": patch.operations[-1]["old_text"],
            "new_text": patch.operations[-1]["new_text"],
        },
        "commands": commands,
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(summary, indent=2, sort_keys=True))
        return

    _print_project_patch_summary(summary)


@project_app.command("apply")
def project_apply(
    project: Annotated[
        str,
        typer.Argument(help="Project id or path"),
    ],
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    config_path = resolve_config_path(config)
    project_dir = resolve_project_dir(project, config_path)
    try:
        spec = load_project(project_dir)
    except ProjectError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    resolved_sot = spec.sot_path
    if sot_path is not None:
        try:
            resolved_sot = resolve_sot_path(sot_path, config_path)
        except (FileNotFoundError, ValueError) as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    try:
        apply_project_patch(project_dir=project_dir, sot_path=resolved_sot)
    except ProjectError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_project_apply_summary(project_dir, resolved_sot)


@tags_app.command("list")
def tags_list(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    payload = load_sot_payload(sot_path, config)
    tags = extract_tags(payload)
    values = sorted({info.normalized for info in tags if info.normalized})

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"tags": values}, indent=2, sort_keys=True))
        return

    for tag in values:
        typer.echo(tag)


@tags_app.command("stats")
def tags_stats(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    payload = load_sot_payload(sot_path, config)
    tags = extract_tags(payload)
    counts = tag_counts(tags)

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"counts": counts}, indent=2, sort_keys=True))
        return

    for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        typer.echo(f"{tag}: {count}")


@tags_app.command("lint")
def tags_lint(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    payload = load_sot_payload(sot_path, config)
    tags = extract_tags(payload)
    issues = lint_tags(tags)

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"issues": issues}, indent=2, sort_keys=True))
    else:
        if issues:
            for issue in issues:
                typer.echo(issue)
        else:
            typer.echo("ok")

    if issues:
        raise typer.Exit(code=1)


@app.command()
def explain(
    item_id: Annotated[
        str,
        typer.Option(
            "--id",
            help="Selection item id to explain",
        ),
    ],
    selection: Annotated[
        Path | None,
        typer.Option(
            "--selection",
            help="Path to selection.json",
        ),
    ] = None,
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id for dist selection lookup",
        ),
    ] = None,
    run: Annotated[
        str | None,
        typer.Option(
            "--run",
            help="Run id or path for selection lookup",
        ),
    ] = None,
    item_type: Annotated[
        str | None,
        typer.Option(
            "--type",
            help="Item type filter (bullet or section)",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    selection_path = resolve_selection_path(selection, config, variant, run)
    try:
        payload = load_selection(selection_path)
        explained = explain_item(payload, item_id, item_type)
    except ExplainError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(explained.item, indent=2, sort_keys=True))
        return

    _print_explain_summary(explained.item)


@app.command(
    help=(
        "Package a built run for human review. Requires an existing run plus "
        "immutable cv.docx, cv.pdf, and selection.json artifacts for the selected run, "
        "project, or variant. `--run` may be combined with `--project` to pin a "
        "specific project-scoped run."
    )
)
def reviewpack(
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id to package for review; cannot be combined with --run or --project",
        ),
    ] = None,
    run: Annotated[
        str | None,
        typer.Option(
            "--run",
            help="Run id or path to package deterministically",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path to package from its latest run; cannot be combined with --variant",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Replace an existing review pack directory explicitly",
        ),
    ] = False,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    if run and variant:
        typer.echo("ERROR: --run cannot be combined with --variant", err=True)
        raise typer.Exit(code=2)
    if project and variant:
        typer.echo("ERROR: --project cannot be combined with --variant", err=True)
        raise typer.Exit(code=2)
    config_path = resolve_config_path(config)
    project_dir = None
    if project is not None:
        try:
            project_dir = resolve_project_dir(project, config_path)
        except ProjectError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    resolved_variant = (
        variant if (run or project_dir) else (variant or resolve_default_variant(config_path))
    )
    try:
        pack = build_review_pack(
            variant_id=resolved_variant,
            config_path=config_path,
            run=run,
            project_dir=project_dir,
            force=force,
        )
    except ReviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        typer.echo(
            _reviewpack_error_hint(
                message=str(exc),
                project=project,
                run=run,
                variant_id=resolved_variant,
            ),
            err=True,
        )
        raise typer.Exit(code=1) from exc

    summary = {
        "out_dir": pack.out_dir,
        "docx": pack.docx_path,
        "pdf": pack.pdf_path,
        "review": pack.review_path,
        "run_id": pack.run_id,
        "source_record": pack.source_record_path,
    }
    _print_reviewpack_summary(summary)


@app.command(
    "import-docx",
    help=(
        "Convert a reviewed DOCX into an import draft. The adjacent review-source.json "
        "pins its baseline. A standalone DOCX requires an explicit `--run`; "
        "variant/project selectors must agree with a recorded source. "
        "When the edited DOCX is a resume "
        "whose Experience bullet or Projects summary text edits map cleanly to "
        "supported source fields, import-docx writes patch.yaml using "
        "structured project-ops; otherwise it falls back to patch.diff against "
        "canonical.md."
    ),
)
def import_docx(
    docx_path: Annotated[
        Path,
        typer.Option(
            "--from",
            help="Path to a DOCX file to import",
        ),
    ],
    run: Annotated[
        str | None,
        typer.Option(
            "--run",
            help="Run id or path to locate canonical markdown; combine with --project to pin a project run",
        ),
    ] = None,
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Require the recorded source variant; cannot be combined with --run or --project",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Require the source project; without a review record also provide --run",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    if run and variant:
        typer.echo("ERROR: --run cannot be combined with --variant", err=True)
        raise typer.Exit(code=2)
    if project and variant:
        typer.echo("ERROR: --project cannot be combined with --variant", err=True)
        raise typer.Exit(code=2)
    if (
        not run
        and not variant
        and not project
        and not (docx_path.parent / SOURCE_RECORD_NAME).exists()
    ):
        typer.echo("ERROR: Provide one of --run, --variant, or --project", err=True)
        raise typer.Exit(code=2)
    config_path = resolve_config_path(config)
    project_dir = None
    if project is not None:
        try:
            project_dir = resolve_project_dir(project, config_path)
        except ProjectError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    try:
        result = import_docx_review(
            docx_path=docx_path,
            config_path=config_path,
            run=run,
            variant_id=variant,
            project_dir=project_dir,
        )
    except ReviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        typer.echo(
            (
                f"HINT: run `{shell_command('reviewpack --variant <variant>')}` or "
                f"`{shell_command('reviewpack --project <project-id>')}` after building review "
                "artifacts, or pass `--run <run-id>` when importing against a specific canonical output."
            ),
            err=True,
        )
        raise typer.Exit(code=1) from exc

    summary = {
        "draft_dir": result.draft_dir,
        "patch": result.patch_path,
        "metadata": result.metadata_path,
        "notes": result.notes_path,
        "imported_markdown": result.imported_path,
        "run_id": result.run_id,
        "apply_status": result.apply_status,
        "next_step": (
            f"Review notes.md, then apply {result.patch_path.name} after explicit approval if draft.json reports ready"
            if result.apply_status == "ready"
            else "Review notes.md; draft.json records a verified no-op"
            if result.apply_status == "ready_no_changes"
            else "Review notes.md and author a real SoT patch manually; draft.json records review_diff_only"
        ),
    }
    _print_import_summary(summary)


@app.command(
    help=(
        "Build deterministic artifacts for a configured variant or a project proposal. "
        "Use exactly one of `--variant` or `--project`; --variant cannot be combined "
        "with --project, and --project cannot be combined with --variant."
    )
)
def build(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id to build; cannot be combined with --project",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path; cannot be combined with --variant",
        ),
    ] = None,
    formats: Annotated[
        list[str] | None,
        typer.Option(
            "--format",
            help="Output formats to render (repeatable or comma-separated)",
        ),
    ] = None,
    theme: Annotated[
        str | None,
        typer.Option(
            "--theme",
            help="Theme id to use for rendering",
        ),
    ] = None,
    style_preset: Annotated[
        str | None,
        typer.Option(
            "--style-preset",
            help="Style preset to apply",
        ),
    ] = None,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        configuration = read_config(config)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    project_spec = None
    variant_path_override = None
    run_dir = None
    if project:
        project_dir = resolve_project_dir(project, configuration)
        try:
            project_spec = load_project(project_dir)
        except ProjectError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        if variant:
            typer.echo("ERROR: --variant cannot be combined with --project", err=True)
            raise typer.Exit(code=2)
        variant_path_override = project_spec.variant_path
        try:
            resolved = resolve_active_sot_path(project_spec.sot_path)
        except SotVersionError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        if sot_path is not None:
            try:
                resolved = resolve_sot_path(sot_path, configuration)
            except (FileNotFoundError, ValueError) as exc:
                typer.echo(f"ERROR: {exc}", err=True)
                raise typer.Exit(code=1) from exc
        runs_root = resolve_runs_path(configuration) / "projects" / project_spec.project_id
        runs_root.mkdir(parents=True, exist_ok=True)
        run_dir = create_run_dir(runs_root)
        try:
            resolved = prepare_project_sot(
                project_dir=project_spec.project_dir,
                sot_path=resolved,
                target_dir=run_dir / "sot",
            )
        except ProjectError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    else:
        try:
            resolved = resolve_sot_path(sot_path, configuration)
        except (FileNotFoundError, ValueError) as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    errors = _validate_sot(resolved)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)

    parsed_formats = _parse_formats(formats)
    try:
        result = build_documents(
            sot_path=resolved,
            config_path=configuration,
            variant_id=variant,
            formats=parsed_formats,
            theme=theme,
            style_preset=style_preset,
            variant_path_override=variant_path_override,
            run_dir=run_dir,
            dist_dir=run_dir if project_spec is not None else None,
        )
    except (ValueError, RenderError, ThemeError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_build_summary(result)


@app.command()
def render(
    canonical: Annotated[
        Path,
        typer.Option(
            "--canonical",
            help="Path to canonical markdown input",
        ),
    ],
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id to render",
        ),
    ] = None,
    formats: Annotated[
        list[str] | None,
        typer.Option(
            "--format",
            help="Output formats to render (repeatable or comma-separated)",
        ),
    ] = None,
    theme: Annotated[
        str | None,
        typer.Option(
            "--theme",
            help="Theme id to use for rendering",
        ),
    ] = None,
    style_preset: Annotated[
        str | None,
        typer.Option(
            "--style-preset",
            help="Style preset to apply",
        ),
    ] = None,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    if not canonical.exists():
        typer.echo(f"ERROR: Canonical markdown not found: {canonical}", err=True)
        raise typer.Exit(code=1)

    try:
        configuration = read_config(config)
        resolved_variant = variant or resolve_default_variant(configuration)
        variant_path = resolve_variant_path(resolved_variant, configuration)
        resolved = load_variant(variant_path)
        dist_dir = resolve_dist_path(configuration) / resolved.id
        pdf_engine = resolve_pdf_engine(configuration)
        theme_id = theme or resolved.render_theme or resolve_default_theme(configuration)
        preset = style_preset or resolved.render_style_preset or resolve_style_preset(configuration)
        theme_dir = resolve_themes_dir(configuration)
        theme_obj = resolve_theme(theme_dir, theme_id)
    except (FileNotFoundError, ValueError, ThemeError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    parsed_formats = _parse_formats(formats)
    selected_formats = resolved.outputs if parsed_formats is None else parsed_formats
    parsed_formats = normalize_output_formats(selected_formats)
    if not parsed_formats:
        typer.echo("ERROR: No output formats selected", err=True)
        raise typer.Exit(code=1)
    try:
        render_plans = {
            fmt: build_render_plan(
                output_format=fmt, theme=theme_obj, style_preset=preset, pdf_engine=pdf_engine
            )
            for fmt in parsed_formats
        }
    except (RenderError, ThemeError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    dist_dir.mkdir(parents=True, exist_ok=True)
    filters_path = filters_dir()
    resolved_filter_paths = resolve_filter_paths(filters_path)
    render_requests: list[RenderRequest] = []
    output_files: dict[str, Path] = {}
    for fmt in parsed_formats:
        output_file = output_path(dist_dir, resolved, fmt)
        try:
            plan = render_plans[fmt]
            if fmt == "html":
                plan = prepare_html_style(dist_dir, plan, theme_obj.id, preset)
            render_requests.append(
                RenderRequest(
                    input_path=canonical,
                    output_path=output_file,
                    variant=resolved,
                    filters_dir=filters_path,
                    output_format=fmt,
                    pdf_engine=pdf_engine,
                    render_plan=plan,
                )
            )
        except (RenderError, ThemeError) as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    def _record_render_success(request: RenderRequest) -> None:
        output_files[request.output_format] = request.output_path

    try:
        render_documents(
            render_requests,
            filter_paths=resolved_filter_paths,
            after_each_success=_record_render_success,
        )
    except RenderError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_render_summary(canonical, resolved.id, dist_dir, output_files)


@dev_app.command("serve")
def dev_serve(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id to build for preview",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path",
        ),
    ] = None,
    theme: Annotated[
        str | None,
        typer.Option(
            "--theme",
            help="Theme id to use for rendering",
        ),
    ] = None,
    style_preset: Annotated[
        str | None,
        typer.Option(
            "--style-preset",
            help="Style preset to apply",
        ),
    ] = None,
    once: Annotated[
        bool,
        typer.Option(
            "--once",
            help="Build once and exit without starting the preview server",
        ),
    ] = False,
    with_pdf: Annotated[
        bool,
        typer.Option(
            "--with-pdf",
            help="With --once, also render a PDF alongside HTML",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    _reject_legacy_preview_env()
    preview = _preview_runtime()
    config_path = resolve_config_path(config)
    project_spec = None
    try:
        if project:
            project_dir = resolve_project_dir(project, config_path)
            project_spec = load_project(project_dir)
            if variant:
                typer.echo("ERROR: --variant cannot be combined with --project", err=True)
                raise typer.Exit(code=2)
            resolved_variant_obj = load_variant(project_spec.variant_path)
            resolved_variant = resolved_variant_obj.id
            resolved = resolve_active_sot_path(project_spec.sot_path)
            if sot_path is not None:
                resolved = resolve_sot_path(sot_path, config_path)
        else:
            resolved = resolve_sot_path(sot_path, config_path)
            resolved_variant = variant or resolve_default_variant(config_path)
            variant_path = resolve_variant_path(resolved_variant, config_path)
            resolved_variant_obj = load_variant(variant_path)
        resolved_theme = (
            theme or resolved_variant_obj.render_theme or resolve_default_theme(config_path)
        )
        resolved_preset = (
            style_preset
            or resolved_variant_obj.render_style_preset
            or resolve_style_preset(config_path)
        )
    except (FileNotFoundError, ValueError, SotVersionError, ProjectError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if sot_path is not None:
        sot_base = resolved
    else:
        try:
            sot_base = resolve_versioned_root(resolved)
        except SotVersionError:
            sot_base = resolved

    one_shot = once or os.environ.get("CVW_DEV_ONCE") == "1"
    session_id = uuid.uuid4().hex
    try:
        controller = preview.PreviewController(
            sot_base=sot_base,
            config_path=config_path,
            variant_id=resolved_variant,
            theme_id=resolved_theme,
            style_preset=resolved_preset,
            auto_pdf=(not one_shot) or with_pdf,
            project_dir=project_spec.project_dir if project_spec else None,
            project_sot_override=sot_base if project_spec and sot_path is not None else None,
            session_id=session_id,
        )
    except preview.PreviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    host = os.environ.get("CVW_DEV_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("CVW_DEV_PORT", "8765"))
    except ValueError as exc:
        typer.echo("ERROR: CVW_DEV_PORT must be an integer", err=True)
        raise typer.Exit(code=1) from exc
    try:
        idle_timeout_seconds = float(os.environ.get("CVW_DEV_IDLE_TIMEOUT_SECONDS", "30"))
    except ValueError as exc:
        typer.echo("ERROR: CVW_DEV_IDLE_TIMEOUT_SECONDS must be numeric", err=True)
        raise typer.Exit(code=1) from exc
    if idle_timeout_seconds < 0:
        typer.echo("ERROR: CVW_DEV_IDLE_TIMEOUT_SECONDS must be >= 0", err=True)
        raise typer.Exit(code=1)
    if one_shot:
        try:
            state = controller.build_once()
        except preview.PreviewError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        html_path = state.output_files.get("html", state.dist_dir / "cv.html")
        _print_serve_summary(
            html_path,
            str(html_path),
            False,
        )
        return

    try:
        host = _validate_preview_host(host)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    session_path = preview.preview_session_path(config_path)
    if session_path.exists():
        try:
            existing_session = preview.load_preview_session(config_path)
        except preview.PreviewError:
            preview.clear_preview_session(config_path)
        else:
            has_conflict, detail = _preview_session_conflict(existing_session)
            if has_conflict:
                typer.echo(f"ERROR: {detail}", err=True)
                typer.echo(
                    (
                        "HINT: reuse the existing preview URL or run "
                        f"`{shell_command('dev stop')}` before starting a new session."
                    ),
                    err=True,
                )
                raise typer.Exit(code=1)
            preview.clear_preview_session(config_path)

    def _on_start(url: str, html_path: Path) -> None:
        session = preview.new_preview_session(
            host=host,
            port=port,
            url=url,
            state=controller.state(),
            session_id=session_id,
            project_id=controller.project_id(),
        )
        preview.write_preview_session(session, config_path)
        _print_serve_summary(
            html_path,
            url,
            True,
        )

    try:
        serve_preview(
            controller=controller,
            host=host,
            port=port,
            idle_timeout_seconds=idle_timeout_seconds,
            on_start=_on_start,
        )
    except preview.PreviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        if exc.errno in {48, 98, 10048}:
            typer.echo(f"ERROR: {exc}", err=True)
            typer.echo(
                (
                    "HINT: preview port is already in use. Run "
                    f"`{shell_command('dev stop')}` or set CVW_DEV_PORT."
                ),
                err=True,
            )
            raise typer.Exit(code=1) from exc
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    finally:
        preview.clear_preview_session(config_path)


@dev_app.command("stop")
def dev_stop(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Force stop by terminating the preview process",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    preview = _preview_runtime()
    config_path = resolve_config_path(config)
    try:
        session = preview.load_preview_session(config_path)
    except preview.PreviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    ok, error = _post_preview_stop(session.url)
    if not ok:
        if force:
            if _preview_pid_is_live(session.pid):
                _terminate_preview_process(session.pid)
        else:
            has_conflict, _detail = _preview_session_conflict(session)
            if has_conflict:
                typer.echo(f"ERROR: {error}", err=True)
                raise typer.Exit(code=1)
            preview.clear_preview_session(config_path)
            print_summary(
                "dev.stop",
                [
                    ("status", "cleared-stale-session"),
                    ("host", session.host),
                    ("port", session.port),
                ],
            )
            return

    if not _wait_for_port_close(session.host, session.port):
        if force:
            if not _preview_pid_is_live(session.pid):
                typer.echo(
                    f"ERROR: Preview port is still in use at {session.host}:{session.port}",
                    err=True,
                )
                raise typer.Exit(code=1)
            _terminate_preview_process(session.pid)
            if not _wait_for_port_close(session.host, session.port):
                typer.echo("ERROR: Preview server still running", err=True)
                raise typer.Exit(code=1)
        else:
            has_conflict, _detail = _preview_session_conflict(session)
            if has_conflict:
                typer.echo("ERROR: Preview server still running", err=True)
                raise typer.Exit(code=1)
            preview.clear_preview_session(config_path)
            print_summary(
                "dev.stop",
                [
                    ("status", "cleared-stale-session"),
                    ("host", session.host),
                    ("port", session.port),
                ],
            )
            return

    preview.clear_preview_session(config_path)
    print_summary(
        "dev.stop",
        [
            ("status", "stopped"),
            ("host", session.host),
            ("port", session.port),
        ],
    )


@app.command(
    help=(
        "Start the local preview server or build one-shot preview output. "
        "Use exactly one of `--variant` or `--project`; --variant cannot be combined "
        "with --project, and --project cannot be combined with --variant. "
        "non-local bind addresses are not supported."
    )
)
def preview(
    sot_path: Annotated[
        Path | None,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id to build for preview; cannot be combined with --project",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path; cannot be combined with --variant",
        ),
    ] = None,
    theme: Annotated[
        str | None,
        typer.Option(
            "--theme",
            help="Theme id to use for rendering",
        ),
    ] = None,
    style_preset: Annotated[
        str | None,
        typer.Option(
            "--style-preset",
            help="Style preset to apply",
        ),
    ] = None,
    once: Annotated[
        bool,
        typer.Option(
            "--once",
            help="Build once and exit without starting the preview server",
        ),
    ] = False,
    with_pdf: Annotated[
        bool,
        typer.Option(
            "--with-pdf",
            help="With --once, also render a PDF alongside HTML",
        ),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    dev_serve(
        sot_path=sot_path,
        config=config,
        variant=variant,
        project=project,
        theme=theme,
        style_preset=style_preset,
        once=once,
        with_pdf=with_pdf,
        plain=plain,
        json_output=json_output,
    )


@app.command()
def tailor(
    job: Annotated[
        Path,
        typer.Option(
            "--job",
            help="Path to a job description file",
        ),
    ],
    out: Annotated[
        Path,
        typer.Option(
            "--out",
            help="Output directory for draft files",
        ),
    ],
    base_variant: Annotated[
        str,
        typer.Option(
            "--base-variant",
            help="Base variant id to start from",
        ),
    ] = "base",
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        resolved_out = resolve_project_path(out, config)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    try:
        paths = tailor_job(
            job_path=job,
            base_variant_id=base_variant,
            output_dir=resolved_out,
            config_path=config,
        )
    except TailorError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_tailor_summary(paths, resolved_out, base_variant)


@app.command()
def apply(
    draft: Annotated[
        Path,
        typer.Option(
            "--draft",
            help="Draft directory containing patch.diff or patch.yaml",
        ),
    ],
    sot_path: Annotated[
        Path,
        typer.Option(
            "--sot-path",
            help="Path to the private Source of Truth directory",
        ),
    ],
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        result = apply_draft(draft_dir=draft, sot_path=sot_path)
    except (ApplyError, ProjectError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_apply_summary(draft, result.patch_path, result.status, result.reason, sot_path)


@app.command()
def diff(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    artifact: Annotated[
        str | None,
        typer.Option(
            "--artifact",
            help="Artifact type (rendered, canonical, resume) with optional :format",
        ),
    ] = None,
    artifact_a: Annotated[
        str | None,
        typer.Option(
            "--artifact-a",
            help="Artifact type for side A",
        ),
    ] = None,
    artifact_b: Annotated[
        str | None,
        typer.Option(
            "--artifact-b",
            help="Artifact type for side B",
        ),
    ] = None,
    run: Annotated[
        str | None,
        typer.Option(
            "--run",
            help="Run id or path to use for both sides",
        ),
    ] = None,
    run_a: Annotated[
        str | None,
        typer.Option(
            "--run-a",
            help="Run id or path for side A",
        ),
    ] = None,
    run_b: Annotated[
        str | None,
        typer.Option(
            "--run-b",
            help="Run id or path for side B",
        ),
    ] = None,
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id for both sides",
        ),
    ] = None,
    variant_a: Annotated[
        str | None,
        typer.Option(
            "--variant-a",
            help="Variant id for side A",
        ),
    ] = None,
    variant_b: Annotated[
        str | None,
        typer.Option(
            "--variant-b",
            help="Variant id for side B",
        ),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Output format: unified or json",
        ),
    ] = "unified",
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    selection_a = DiffSelection(
        artifact=parse_artifact(artifact_a or artifact),
        run=run_a or run,
        variant=variant_a or variant,
    )
    selection_b = DiffSelection(
        artifact=parse_artifact(artifact_b or artifact),
        run=run_b or run,
        variant=variant_b or variant,
    )

    try:
        diff_text, summary = diff_artifacts(
            config_path=config,
            selection_a=selection_a,
            selection_b=selection_b,
        )
    except DiffError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if output_format == "json":
        typer.echo(json.dumps(summary, indent=2, sort_keys=True))
        return

    if output_format != "unified":
        typer.echo(f"ERROR: Unknown output format: {output_format}", err=True)
        raise typer.Exit(code=1)

    if get_output_mode() == OutputMode.JSON:
        payload = {"summary": summary, "diff": diff_text}
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    _print_diff_summary(summary)
    if diff_text:
        typer.echo(diff_text)


@app.command()
def compare(
    run_a: Annotated[
        str,
        typer.Option(
            "--run-a",
            help="Run id or path for side A",
        ),
    ],
    run_b: Annotated[
        str,
        typer.Option(
            "--run-b",
            help="Run id or path for side B",
        ),
    ],
    out_dir: Annotated[
        Path | None,
        typer.Option(
            "--out-dir",
            help="Directory to write rasterized pages and the HTML report",
        ),
    ] = None,
    dpi: Annotated[
        int,
        typer.Option(
            "--dpi",
            help="Rasterization DPI for PDF pages",
        ),
    ] = 144,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use plain text output (no Rich panels)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Use JSON output for summaries",
        ),
    ] = False,
) -> None:
    configure_output_mode(plain, json_output)
    try:
        result = compare_rendered_pdfs(
            config_path=config,
            run_a=run_a,
            run_b=run_b,
            out_dir=out_dir,
            dpi=dpi,
        )
    except RenderCompareError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    summary = {
        "command": "compare",
        "status": result.status,
        "run_a": {
            "run_id": result.run_a.run_id,
            "path": str(result.run_a.path),
            "pdf": str(result.pdf_a),
        },
        "run_b": {
            "run_id": result.run_b.run_id,
            "path": str(result.run_b.path),
            "pdf": str(result.pdf_b),
        },
        "page_count_a": sum(1 for page in result.pages if page.image_a is not None),
        "page_count_b": sum(1 for page in result.pages if page.image_b is not None),
        "identical_pages": sum(1 for page in result.pages if page.identical),
        "different_pages": sum(1 for page in result.pages if not page.identical),
        "out_dir": str(result.out_dir),
        "report": str(result.report_path),
        "summary_json": str(result.summary_path),
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps(summary, indent=2, sort_keys=True))
        return

    _print_compare_summary(summary)
