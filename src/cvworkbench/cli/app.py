"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/app.py

Command-line interface for the CV workbench.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import os
import signal
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from urllib import error as url_error
from urllib import request as url_request

import typer
import yaml

from cvworkbench.build.explain import ExplainError, explain_item, load_selection
from cvworkbench.build.paths import filters_dir, output_path
from cvworkbench.build.pipeline import BuildResult, build_documents, create_run_dir
from cvworkbench.build.rendering import RenderError, render_document
from cvworkbench.build.styles import prepare_html_style
from cvworkbench.cli.helpers import configure_output_mode, load_sot_payload, resolve_selection_path
from cvworkbench.cli.output import OutputMode, get_output_mode, print_summary
from cvworkbench.config import (
    load_config,
    resolve_config_path,
    resolve_default_theme,
    resolve_default_variant,
    resolve_dist_path,
    resolve_drafts_path,
    resolve_pdf_engine,
    resolve_project_path,
    resolve_projects_path,
    resolve_registry_path,
    resolve_reviews_path,
    resolve_runs_path,
    resolve_sot_path,
    resolve_style_preset,
    resolve_sync_mode,
    resolve_themes_dir,
    resolve_var_root,
    resolve_variant_ttl_days,
    resolve_variant_path,
)
from cvworkbench.dev.preview import (
    PreviewController,
    PreviewError,
    clear_preview_session,
    load_preview_session,
    new_preview_session,
    serve_preview,
    write_preview_session,
)
from cvworkbench.ingestion.registry import RegistryError, add_url_context
from cvworkbench.inputs.sot import OPTIONAL_FILES, REQUIRED_FILES, load_sot
from cvworkbench.inputs.sot_versions import (
    SotVersionError,
    resolve_active_sot_path,
    resolve_versioned_root,
)
from cvworkbench.inputs.tags import extract_tags, lint_tags, tag_counts
from cvworkbench.inputs.validation import validate_sot
from cvworkbench.ops.apply import ApplyError, apply_draft
from cvworkbench.ops.clean import CleanError, clean_path
from cvworkbench.ops.diffing import DiffError, DiffSelection, diff_artifacts, parse_artifact
from cvworkbench.ops.doctor import run_doctor
from cvworkbench.ops.projects import (
    ProjectError,
    apply_project_patch,
    create_project_from_file,
    create_project_from_url,
    load_project,
    prepare_project_sot,
    resolve_project_dir,
)
from cvworkbench.ops.runs import (
    RunError,
    RunGcCandidate,
    RunGcSummary,
    RunInfo,
    gc_runs,
    latest_runs_by_variant,
    resolve_latest_run,
)
from cvworkbench.ops.review import ReviewError, build_review_pack, import_docx_review
from cvworkbench.ops.scaffold import ScaffoldError, init_project, resolve_template_root
from cvworkbench.ops.sot_versions import (
    SotPackError,
    activate_version,
    create_version,
    diff_versions,
    list_versions,
)
from cvworkbench.ops.syncing import SyncError, SyncResult, sync_site
from cvworkbench.ops.tailor import DraftPaths, TailorError, tailor_job
from cvworkbench.ops.variant_lifecycle import (
    VariantLifecycleError,
    discard_variant,
    gc_variants,
    keep_variant,
    list_variant_inbox,
)
from cvworkbench.ops.variant_promote import PromoteError, promote_variant
from cvworkbench.themes import ThemeError, build_render_plan, list_themes, resolve_theme
from cvworkbench.text import normalize_tag
from cvworkbench.variants import load_variant

app = typer.Typer(add_completion=False, no_args_is_help=True)
job_app = typer.Typer(no_args_is_help=True)
tags_app = typer.Typer(no_args_is_help=True)
theme_app = typer.Typer(no_args_is_help=True)
dev_app = typer.Typer(no_args_is_help=True)
variant_app = typer.Typer(no_args_is_help=True)
clean_app = typer.Typer(no_args_is_help=True)
sot_app = typer.Typer(no_args_is_help=True)
project_app = typer.Typer(no_args_is_help=True)
runs_app = typer.Typer(no_args_is_help=True)
app.add_typer(job_app, name="job")
app.add_typer(tags_app, name="tags")
app.add_typer(theme_app, name="theme")
app.add_typer(dev_app, name="dev")
app.add_typer(variant_app, name="variant")
app.add_typer(runs_app, name="runs")
app.add_typer(clean_app, name="clean")
app.add_typer(sot_app, name="sot")
app.add_typer(project_app, name="project")


def _not_implemented(command: str) -> None:
    typer.echo(f"{command} is not implemented yet", err=True)
    raise typer.Exit(code=2)


def _parse_formats(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    formats: list[str] = []
    for value in values:
        parts = [part.strip() for part in value.split(",") if part.strip()]
        formats.extend(parts)
    return formats


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


def _print_sync_summary(result: SyncResult) -> None:
    plan = result.plan
    changed_files = len(plan.copy_ops)
    if plan.frontmatter_content:
        changed_files += 1
    status = "no_changes"
    if plan.has_changes():
        status = "pr_created" if result.mode == "pr" else "applied"

    rows: list[tuple[str, str | Path]] = [
        ("sync_mode", result.mode),
        ("sync_status", status),
        ("site_repo", result.site.repo_path),
        ("pdf_url", plan.pdf_url),
        ("files_updated", str(changed_files)),
    ]
    if result.branch:
        rows.append(("branch", result.branch))
    print_summary("sync", rows)


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
    rows = [
        ("config", summary["config"]["path"]),
        ("sot_status", summary["sot"]["status"]),
        ("sot_path", sot_path),
        ("variants", summary["variants"]["summary"]),
        ("runs_latest", summary["runs"]["latest_summary"]),
        ("projects", summary["projects"]["summary"]),
        ("recipes", ", ".join([recipe["id"] for recipe in summary["recipes"]])),
    ]
    if summary["issues"]:
        rows.append(("issues", "; ".join(summary["issues"])))
    print_summary("context", rows)


def _configured_sot_path(sot_path: Path | None, config_path: Path) -> str | None:
    if sot_path is not None:
        return str(sot_path)
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError):
        return None
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        return None
    value = paths.get("sot")
    if not isinstance(value, str) or not value.strip():
        return None
    return str((config_path.parent / value.strip()).resolve())


def _build_sot_details(resolved_sot: Path, payload: dict[str, Any]) -> dict[str, Any]:
    files = _collect_sot_files(resolved_sot)
    files_summary = _files_summary_line(files)
    sections = _summarize_sot_sections(payload)
    sections_summary = _summarize_sections_line(sections)
    tags = extract_tags(payload)
    counts = tag_counts(tags)
    tags_top = _top_tags(counts)
    tags_summary = _tags_summary_line(tags_top)
    return {
        "files": files,
        "files_summary": files_summary,
        "sections": sections,
        "sections_summary": sections_summary,
        "tags_top": tags_top,
        "tags_summary": tags_summary,
    }


def _build_versions_info(resolved_sot: Path) -> tuple[dict[str, Any] | None, str, str | None]:
    try:
        version_root = resolve_versioned_root(resolved_sot)
    except SotVersionError:
        return None, "", None
    try:
        version_state = list_versions(version_root)
    except SotPackError as exc:
        return None, "", str(exc)
    versions_info = {
        "root": str(version_state.root),
        "active": version_state.active,
        "versions": version_state.versions,
    }
    versions_summary = (
        f"root={version_state.root} active={version_state.active} "
        f"count={len(version_state.versions)}"
    )
    return versions_info, versions_summary, None


def _build_context_recipes(
    *,
    sot_path: Path | None,
    default_variant: str | None,
    projects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sot_label = str(sot_path) if sot_path else "<sot-path>"
    variant_label = default_variant or "<variant-id>"
    project_label = projects[0]["project_id"] if projects else "<project-id>"
    return [
        {
            "id": "context.refresh",
            "title": "Refresh context",
            "steps": [
                {
                    "command": "cvw context --json",
                    "description": "Re-scan workspace state for SoT, variants, runs, and projects.",
                }
            ],
        },
        {
            "id": "sot.inspect",
            "title": "Inspect SoT inventory",
            "steps": [
                {
                    "command": f"cvw status --sot-path {sot_label}",
                    "description": "Summarize SoT sections, tags, and configured variants.",
                }
            ],
        },
        {
            "id": "build.default",
            "title": "Build the default variant",
            "steps": [
                {
                    "command": f"cvw build --sot-path {sot_label} --variant {variant_label} --format md,pdf",
                    "description": "Generate markdown and PDF outputs for the default variant.",
                }
            ],
        },
        {
            "id": "preview.default",
            "title": "Preview the default variant",
            "steps": [
                {
                    "command": f"cvw preview --sot-path {sot_label} --variant {variant_label}",
                    "description": "Start the local preview server for the default variant.",
                }
            ],
        },
        {
            "id": "project.guide",
            "title": "Start a job-tailoring project",
            "steps": [
                {
                    "command": f"cvw project guide --job-url <job-url> --sot-path {sot_label}",
                    "description": "Ingest a job posting and get variant recommendations.",
                }
            ],
        },
        {
            "id": "project.preview",
            "title": "Preview a project",
            "steps": [
                {
                    "command": f"cvw preview --project {project_label}",
                    "description": "Preview with the project patch applied in-memory.",
                },
                {
                    "command": f"cvw project apply {project_label}",
                    "description": "Apply the project patch to the SoT on disk.",
                },
            ],
        },
        {
            "id": "variant.manage",
            "title": "Promote or discard variants",
            "steps": [
                {
                    "command": "cvw variant inbox",
                    "description": "List ephemeral variants awaiting a keep/discard decision.",
                },
                {
                    "command": "cvw variant keep --path <variant.yaml> --id <variant-id>",
                    "description": "Promote a draft/project variant into config/variants.",
                },
                {
                    "command": "cvw variant discard --path <variant.yaml> --yes",
                    "description": "Discard draft/project variant artifacts.",
                },
            ],
        },
        {
            "id": "runs.gc",
            "title": "Prune older runs",
            "steps": [
                {
                    "command": "cvw runs gc --keep-latest 2",
                    "description": "See which runs would be removed (dry run).",
                },
                {
                    "command": "cvw runs gc --keep-latest 2 --yes",
                    "description": "Delete runs older than the keep window.",
                },
            ],
        },
    ]


def _record_context_issue(message: str, issues: list[str], strict: bool) -> None:
    if strict:
        typer.echo(f"ERROR: {message}", err=True)
        raise typer.Exit(code=1)
    issues.append(message)


def _format_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _collect_sot_files(sot_path: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for filename in list(REQUIRED_FILES.keys()) + list(OPTIONAL_FILES.keys()):
        path = sot_path / filename
        if path.exists():
            files.append(
                {
                    "name": filename,
                    "path": str(path),
                    "status": "present",
                    "modified_at": _format_timestamp(path.stat().st_mtime),
                }
            )
        else:
            files.append(
                {
                    "name": filename,
                    "path": str(path),
                    "status": "missing",
                    "modified_at": None,
                }
            )
    return files


def _files_summary_line(files: list[dict[str, Any]]) -> str:
    present = [item["name"] for item in files if item["status"] == "present"]
    missing = [item["name"] for item in files if item["status"] == "missing"]
    parts: list[str] = []
    if present:
        parts.append("present: " + ", ".join(present))
    if missing:
        parts.append("missing: " + ", ".join(missing))
    return "; ".join(parts) if parts else "none"


def _count_list_section(payload: dict[str, Any], section: str, key: str) -> int:
    data = payload.get(section)
    if not isinstance(data, dict):
        return 0
    values = data.get(key)
    if not isinstance(values, list):
        return 0
    return len(values)


def _summarize_sot_sections(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    experience = payload.get("experience")
    roles_count = 0
    bullets_count = 0
    if isinstance(experience, dict):
        roles = experience.get("roles")
        if isinstance(roles, list):
            roles_count = len(roles)
            for role in roles:
                if not isinstance(role, dict):
                    continue
                bullets = role.get("bullets")
                if isinstance(bullets, list):
                    bullets_count += len(bullets)
    summary["experience"] = {"roles": roles_count, "bullets": bullets_count}
    summary["projects"] = {"count": _count_list_section(payload, "projects", "projects")}
    summary["skills"] = {"count": _count_list_section(payload, "skills", "skills")}
    summary["education"] = {"count": _count_list_section(payload, "education", "education")}
    summary["publications"] = {"count": _count_list_section(payload, "publications", "publications")}
    summary["honors"] = {"count": _count_list_section(payload, "honors", "honors")}
    summary["service"] = {"count": _count_list_section(payload, "service", "service")}
    summary["teaching"] = {"count": _count_list_section(payload, "teaching", "teaching")}
    summary["conferences"] = {"count": _count_list_section(payload, "conferences", "conferences")}
    summary["references"] = {"count": _count_list_section(payload, "references", "references")}
    letters_count = 0
    letter_sections = 0
    letters = payload.get("letters")
    if isinstance(letters, dict):
        letter_list = letters.get("letters")
        if isinstance(letter_list, list):
            letters_count = len(letter_list)
            for letter in letter_list:
                if not isinstance(letter, dict):
                    continue
                sections = letter.get("sections")
                if isinstance(sections, list):
                    letter_sections += len(sections)
    summary["letters"] = {"letters": letters_count, "sections": letter_sections}
    snippets_count = 0
    snippets = payload.get("snippets")
    if isinstance(snippets, dict):
        snippet_list = snippets.get("snippets")
        if isinstance(snippet_list, list):
            snippets_count = len(snippet_list)
    summary["snippets"] = {"count": snippets_count}
    return summary


def _summarize_sections_line(summary: dict[str, Any]) -> str:
    parts: list[str] = []
    experience = summary.get("experience", {})
    parts.append(
        f"experience roles={experience.get('roles', 0)} bullets={experience.get('bullets', 0)}"
    )
    for key in [
        "projects",
        "skills",
        "education",
        "publications",
        "conferences",
        "honors",
        "service",
        "teaching",
        "references",
    ]:
        count = summary.get(key, {}).get("count", 0)
        parts.append(f"{key}={count}")
    letters = summary.get("letters", {})
    parts.append(f"letters={letters.get('letters', 0)} sections={letters.get('sections', 0)}")
    snippets = summary.get("snippets", {})
    parts.append(f"snippets={snippets.get('count', 0)}")
    return "; ".join(parts)


def _top_tags(counts: dict[str, int], limit: int = 10) -> list[dict[str, Any]]:
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"tag": tag, "count": count} for tag, count in ordered[:limit]]


def _tags_summary_line(tags: list[dict[str, Any]]) -> str:
    if not tags:
        return "none"
    return ", ".join([f"{item['tag']}({item['count']})" for item in tags])


def _variants_dir(config_path: Path) -> Path:
    return config_path.parent / "variants"


def _load_variants_from_config(config_path: Path) -> list[dict[str, Any]]:
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


def _variants_summary_line(variants: list[dict[str, Any]]) -> str:
    return ", ".join(
        [f"{variant['id']} ({variant['document_type']})" for variant in variants]
    )


def _inbox_entry_payload(entry: Any) -> dict[str, Any]:
    return {
        "variant_id": entry.variant_id,
        "variant_path": str(entry.variant_path),
        "source": entry.source,
        "status": entry.status,
        "expires_at": entry.expires_at,
        "label": entry.label,
    }


def _inbox_summary_line(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "count=0"
    lines = [f"{entry['label'] or entry['variant_id']} | {entry['source']} | {entry['expires_at']}" for entry in entries]
    return f"count={len(entries)}\n" + "\n".join(lines)


def _run_payload(run: RunInfo) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "path": str(run.path),
        "created_at": run.created_at.isoformat(),
        "variant_id": run.variant_id,
        "formats": run.formats,
        "outputs": run.outputs,
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
    print_summary("runs.gc", rows)


def _runs_summary_line(latest: dict[str, list[dict[str, Any]]]) -> str:
    if not latest:
        return "none"
    lines = []
    for variant_id, runs in latest.items():
        if not runs:
            continue
        lines.append(f"{variant_id}: {runs[0]['run_id']}")
    return "\n".join(lines) if lines else "none"


def _runs_recents_line(recents: dict[str, list[dict[str, Any]]]) -> str:
    if not recents:
        return "none"
    lines = []
    for variant_id, runs in recents.items():
        if not runs:
            continue
        run_ids = ", ".join([run["run_id"] for run in runs])
        lines.append(f"{variant_id}: {run_ids}")
    return "\n".join(lines) if lines else "none"


def _invalid_runs_line(paths: list[Path]) -> str:
    if not paths:
        return ""
    return ", ".join([path.name for path in paths])


def _load_project_summaries(config_path: Path) -> tuple[list[dict[str, Any]], list[Path]]:
    projects_root = resolve_projects_path(config_path)
    if not projects_root.exists():
        return [], []
    summaries: list[dict[str, Any]] = []
    invalid: list[Path] = []
    for path in sorted([p for p in projects_root.iterdir() if p.is_dir()]):
        project_file = path / "project.yaml"
        if not project_file.exists():
            invalid.append(path)
            continue
        raw = yaml.safe_load(project_file.read_text())
        if not isinstance(raw, dict):
            invalid.append(path)
            continue
        project = raw.get("project")
        if not isinstance(project, dict):
            invalid.append(path)
            continue
        project_id = str(project.get("id", "")).strip()
        base_variant = str(project.get("base_variant", "")).strip()
        created_at = str(project.get("created_at", "")).strip()
        job = project.get("job", {})
        job_source = None
        if isinstance(job, dict):
            source = job.get("source", {})
            if isinstance(source, dict):
                job_source = source.get("value") or source.get("type")
        if not project_id or not base_variant:
            invalid.append(path)
            continue
        summaries.append(
            {
                "project_id": project_id,
                "project_dir": str(path),
                "base_variant": base_variant,
                "created_at": created_at or None,
                "job_source": job_source,
            }
        )
    return summaries, invalid


def _projects_summary_line(projects: list[dict[str, Any]]) -> str:
    if not projects:
        return "count=0"
    lines = [f"{item['project_id']} ({item['base_variant']})" for item in projects]
    return f"count={len(projects)}\n" + "\n".join(lines)


def _load_job_signals(signals_path: Path) -> dict[str, Any]:
    if not signals_path.exists():
        raise ValueError(f"Job signals not found: {signals_path}")
    raw = json.loads(signals_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Job signals are invalid: {signals_path}")
    return raw


def _normalize_keywords(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        keyword = normalize_tag(value)
        if keyword and keyword not in seen:
            normalized.append(keyword)
            seen.add(keyword)
    return normalized


def _job_keyword_overlap(job_keywords: list[str], tag_counts: dict[str, int]) -> dict[str, list[str]]:
    job_set = set(job_keywords)
    tag_set = set(tag_counts.keys())
    return {
        "matched": sorted(job_set & tag_set),
        "missing": sorted(job_set - tag_set),
    }


def _recommend_variants(
    variants: list[dict[str, Any]],
    job_keywords: list[str],
    tag_counts: dict[str, int],
    default_variant: str,
) -> list[dict[str, Any]]:
    job_set = set(job_keywords)
    tag_set = set(tag_counts.keys())
    recommendations: list[dict[str, Any]] = []
    for variant in variants:
        include = set(variant.get("include_tags") or [])
        exclude = set(variant.get("exclude_tags") or [])
        include_matches = sorted(include & job_set)
        include_missing = sorted(include - job_set)
        missing_in_sot = sorted(include - tag_set)
        exclude_matches = sorted(exclude & job_set)
        score = len(include_matches)
        eligible = len(exclude_matches) == 0
        recommendations.append(
            {
                "variant_id": variant["id"],
                "document_type": variant["document_type"],
                "score": score,
                "eligible": eligible,
                "default": variant["id"] == default_variant,
                "include_matches": include_matches,
                "include_missing": include_missing,
                "exclude_matches": exclude_matches,
                "missing_in_sot": missing_in_sot,
            }
        )
    recommendations.sort(
        key=lambda item: (not item["eligible"], -item["score"], item["variant_id"])
    )
    for idx, item in enumerate(recommendations, start=1):
        item["rank"] = idx
    return recommendations


def _recommendations_summary_line(recommendations: list[dict[str, Any]], limit: int = 5) -> str:
    if not recommendations:
        return "none"
    lines: list[str] = []
    for item in recommendations[:limit]:
        parts = [item["variant_id"], f"score={item['score']}"]
        if item.get("default"):
            parts.append("default")
        if item.get("include_matches"):
            parts.append("match=" + ",".join(item["include_matches"]))
        if item.get("exclude_matches"):
            parts.append("exclude=" + ",".join(item["exclude_matches"]))
        if item.get("missing_in_sot"):
            parts.append("missing_sot=" + ",".join(item["missing_in_sot"]))
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def _load_review_summaries(config_path: Path) -> list[dict[str, Any]]:
    reviews_root = resolve_reviews_path(config_path)
    if not reviews_root.exists():
        return []
    summaries: list[dict[str, Any]] = []
    for path in sorted([p for p in reviews_root.iterdir() if p.is_dir()]):
        summaries.append(
            {
                "review_id": path.name,
                "path": str(path),
                "docx": str(path / "cv.docx") if (path / "cv.docx").exists() else None,
                "pdf": str(path / "cv.pdf") if (path / "cv.pdf").exists() else None,
                "review": str(path / "review.md") if (path / "review.md").exists() else None,
            }
        )
    return summaries


def _reviews_summary_line(reviews: list[dict[str, Any]]) -> str:
    if not reviews:
        return "count=0"
    lines = [item["review_id"] for item in reviews]
    return f"count={len(reviews)}\n" + "\n".join(lines)


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


def _print_variant_gc_summary(expired: int, kept_pruned: int, status: str) -> None:
    print_summary(
        "variant.gc",
        [
            ("expired", str(expired)),
            ("kept_pruned", str(kept_pruned)),
            ("status", status),
        ],
    )


def _print_variant_inbox(entries: list[Any]) -> None:
    if get_output_mode() == OutputMode.JSON:
        payload = {
            "command": "variant.inbox",
            "entries": [
                {
                    "variant_id": entry.variant_id,
                    "variant_path": str(entry.variant_path),
                    "expires_at": entry.expires_at,
                    "source": entry.source,
                    "label": entry.label,
                }
                for entry in entries
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    lines = [
        f"{entry.variant_id} | {entry.source} | {entry.expires_at} | {entry.variant_path}"
        for entry in entries
    ]
    rows: list[tuple[str, str | Path]] = [
        ("count", str(len(entries))),
    ]
    if lines:
        rows.append(("entries", "\n".join(lines)))
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


def _print_theme_info_summary(theme_id: str, description: str | None, routes: list[str]) -> None:
    rows: list[tuple[str, str | Path]] = [
        ("id", theme_id),
        ("routes", ", ".join(routes)),
    ]
    if description:
        rows.append(("description", description))
    print_summary("theme.info", rows)


def _print_serve_summary(
    output_path: Path,
    preview_url: str,
    watching: bool,
) -> None:
    print_summary(
        "serve",
        [
            ("output_html", output_path),
            ("preview_url", preview_url),
            ("watching", str(watching).lower()),
            ("controls", "t=theme p=preset v=variant f=format r=rebuild x=stop"),
        ],
    )


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


def _wait_for_port_close(host: str, port: int, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                pass
        except OSError:
            return True
        time.sleep(0.1)
    return False


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


def _print_quickstart_summary(result: BuildResult, sample_sot: Path) -> None:
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
    rows.append(("next_step", "cvw preview --sot-path ./sot.sample --variant base"))
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
            ("variant", variant_id),
            ("job_source", job_source),
            ("next_step", f"cvw preview --project {project_dir.name}"),
        ],
    )


def _print_project_guide_summary(summary: dict[str, Any]) -> None:
    rows = [
        ("project_dir", summary["project"]["project_dir"]),
        ("variant", summary["project"]["base_variant"]),
        ("job_source", summary["project"]["job_source"]),
        ("job_keywords", ", ".join(summary["job"]["keywords"]) or "none"),
        ("job_keywords_in_sot", ", ".join(summary["job"]["keywords_in_sot"]) or "none"),
        ("job_keywords_missing", ", ".join(summary["job"]["keywords_missing"]) or "none"),
        ("sot_tags_top", summary["sot"]["tags_summary"]),
        ("recommendations", _recommendations_summary_line(summary["recommendations"])),
        ("next_step", f"cvw preview --project {summary['project']['project_id']}"),
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


def _print_apply_summary(draft_dir: Path, patch_path: Path, status: str, sot_path: Path) -> None:
    print_summary(
        "apply",
        [
            ("draft_dir", draft_dir),
            ("patch", patch_path),
            ("status", status),
            ("sot_path", sot_path),
        ],
    )


@app.command()
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

    errors = validate_sot(resolved)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)
    _print_validate_summary(resolved)


@app.command()
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


@app.command()
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
    config_path = resolve_config_path(config)
    try:
        resolved_sot = resolve_sot_path(sot_path, config_path)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    errors = validate_sot(resolved_sot)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)
    try:
        payload = load_sot(resolved_sot)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    sot_details = _build_sot_details(resolved_sot, payload)
    files = sot_details["files"]
    files_summary = sot_details["files_summary"]
    sections = sot_details["sections"]
    sections_summary = sot_details["sections_summary"]
    tags_top = sot_details["tags_top"]
    tags_summary = sot_details["tags_summary"]

    versions_info, versions_summary, versions_error = _build_versions_info(resolved_sot)
    if versions_error:
        typer.echo(f"ERROR: {versions_error}", err=True)
        raise typer.Exit(code=1)

    try:
        variants = _load_variants_from_config(config_path)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    variants_summary = _variants_summary_line(variants)

    inbox_entries = list_variant_inbox(config_path)
    inbox_payload = [_inbox_entry_payload(entry) for entry in inbox_entries]
    inbox_summary = _inbox_summary_line(inbox_payload)
    ttl_days = resolve_variant_ttl_days(config_path)

    recents_by_variant, invalid_runs = latest_runs_by_variant(config_path, limit=3)
    recents_payload: dict[str, list[dict[str, Any]]] = {}
    for variant in variants:
        runs = recents_by_variant.get(variant["id"], [])
        recents_payload[variant["id"]] = [_run_payload(run) for run in runs]
    latest_payload = {key: value[:1] for key, value in recents_payload.items()}

    latest_summary = _runs_summary_line(latest_payload)
    recents_summary = _runs_recents_line(recents_payload)
    invalid_summary = _invalid_runs_line(invalid_runs)

    projects, invalid_projects = _load_project_summaries(config_path)
    projects_summary = _projects_summary_line(projects)
    invalid_projects_summary = _invalid_runs_line(invalid_projects)

    reviews = _load_review_summaries(config_path)
    reviews_summary = _reviews_summary_line(reviews)

    summary = {
        "sot": {
            "path": str(resolved_sot),
            "files": files,
            "files_summary": files_summary or "none",
            "sections": sections,
            "sections_summary": sections_summary,
            "tags_top": tags_top,
            "tags_summary": tags_summary,
            "versions": versions_info,
            "versions_summary": versions_summary,
        },
        "variants": {
            "config": variants,
            "config_count": len(variants),
            "summary": variants_summary,
            "inbox": inbox_payload,
            "inbox_count": len(inbox_payload),
            "inbox_summary": inbox_summary,
            "ttl_days": ttl_days,
        },
        "runs": {
            "latest_by_variant": latest_payload,
            "recents_by_variant": recents_payload,
            "latest_summary": latest_summary,
            "recents_summary": recents_summary,
            "invalid": [str(path) for path in invalid_runs],
            "invalid_summary": invalid_summary,
        },
        "projects": {
            "items": projects,
            "count": len(projects),
            "summary": projects_summary,
            "invalid": [str(path) for path in invalid_projects],
            "invalid_summary": invalid_projects_summary,
        },
        "reviews": {
            "items": reviews,
            "count": len(reviews),
            "summary": reviews_summary,
        },
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"command": "status", **summary}, indent=2, sort_keys=True))
        return

    _print_status_summary(summary)


@app.command()
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
        config_path = resolve_config_path(config)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    try:
        config_payload = load_config(config_path)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    issues: list[str] = []
    configured_sot = _configured_sot_path(sot_path, config_path)
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
        resolved_sot = resolve_sot_path(sot_path, config_path)
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
        errors = validate_sot(resolved_sot)
        if errors:
            for error in errors:
                _record_context_issue(error, issues, strict)
                sot_errors.append(error)
            sot_status = "invalid"
        else:
            try:
                payload = load_sot(resolved_sot)
            except ValueError as exc:
                _record_context_issue(str(exc), issues, strict)
                sot_errors.append(str(exc))
                sot_status = "invalid"
            else:
                sot_details = _build_sot_details(resolved_sot, payload)
                versions_info, versions_summary, versions_error = _build_versions_info(resolved_sot)
                if versions_error:
                    _record_context_issue(versions_error, issues, strict)
                sot_status = "ready"

    default_variant: str | None = None
    try:
        default_variant = resolve_default_variant(config_path)
    except ValueError as exc:
        _record_context_issue(str(exc), issues, strict)

    variants: list[dict[str, Any]] = []
    try:
        variants = _load_variants_from_config(config_path)
    except ValueError as exc:
        _record_context_issue(str(exc), issues, strict)
    variants_summary = _variants_summary_line(variants) if variants else "none"

    inbox_payload: list[dict[str, Any]] = []
    try:
        inbox_entries = list_variant_inbox(config_path)
        inbox_payload = [_inbox_entry_payload(entry) for entry in inbox_entries]
    except (VariantLifecycleError, ValueError) as exc:
        _record_context_issue(str(exc), issues, strict)
    inbox_summary = _inbox_summary_line(inbox_payload)

    ttl_days: int | None = None
    try:
        ttl_days = resolve_variant_ttl_days(config_path)
    except ValueError as exc:
        _record_context_issue(str(exc), issues, strict)

    recents_payload: dict[str, list[dict[str, Any]]] = {}
    latest_payload: dict[str, list[dict[str, Any]]] = {}
    invalid_runs: list[Path] = []
    try:
        recents_by_variant, invalid_runs = latest_runs_by_variant(config_path, limit=3)
        variant_ids = [variant["id"] for variant in variants]
        if not variant_ids:
            variant_ids = sorted(recents_by_variant.keys())
        for variant_id in variant_ids:
            runs = recents_by_variant.get(variant_id, [])
            recents_payload[variant_id] = [_run_payload(run) for run in runs]
        latest_payload = {key: value[:1] for key, value in recents_payload.items()}
    except (RunError, ValueError) as exc:
        _record_context_issue(str(exc), issues, strict)

    latest_summary = _runs_summary_line(latest_payload)
    recents_summary = _runs_recents_line(recents_payload)
    invalid_summary = _invalid_runs_line(invalid_runs)

    projects: list[dict[str, Any]] = []
    invalid_projects: list[Path] = []
    try:
        projects, invalid_projects = _load_project_summaries(config_path)
    except (ValueError, FileNotFoundError) as exc:
        _record_context_issue(str(exc), issues, strict)
    projects_summary = _projects_summary_line(projects)
    invalid_projects_summary = _invalid_runs_line(invalid_projects)

    reviews: list[dict[str, Any]] = []
    try:
        reviews = _load_review_summaries(config_path)
    except (ValueError, FileNotFoundError) as exc:
        _record_context_issue(str(exc), issues, strict)
    reviews_summary = _reviews_summary_line(reviews)

    project_name: str | None = None
    project_data = config_payload.get("project", {})
    if isinstance(project_data, dict):
        name_value = project_data.get("name")
        if isinstance(name_value, str) and name_value.strip():
            project_name = name_value.strip()

    summary = {
        "config": {
            "path": str(config_path),
            "project": {"name": project_name},
        },
        "sot": {
            "configured_path": configured_sot,
            "path": str(resolved_sot) if resolved_sot else None,
            "status": sot_status,
            "errors": sot_errors,
            "versions": versions_info,
            "versions_summary": versions_summary,
            **sot_details,
        },
        "variants": {
            "config": variants,
            "config_count": len(variants),
            "summary": variants_summary,
            "inbox": inbox_payload,
            "inbox_count": len(inbox_payload),
            "inbox_summary": inbox_summary,
            "ttl_days": ttl_days,
            "default": default_variant,
        },
        "runs": {
            "latest_by_variant": latest_payload,
            "recents_by_variant": recents_payload,
            "latest_summary": latest_summary,
            "recents_summary": recents_summary,
            "invalid": [str(path) for path in invalid_runs],
            "invalid_summary": invalid_summary,
        },
        "projects": {
            "items": projects,
            "count": len(projects),
            "summary": projects_summary,
            "invalid": [str(path) for path in invalid_projects],
            "invalid_summary": invalid_projects_summary,
        },
        "reviews": {
            "items": reviews,
            "count": len(reviews),
            "summary": reviews_summary,
        },
        "recipes": _build_context_recipes(
            sot_path=resolved_sot,
            default_variant=default_variant,
            projects=projects,
        ),
        "issues": issues,
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"command": "context", **summary}, indent=2, sort_keys=True))
        return

    _print_context_summary(summary)


@app.command()
def init(
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
        result = init_project(Path.cwd())
    except ScaffoldError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    statuses = result.statuses
    summary = {
        "root": result.root,
        "sot_path": result.sot_path,
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
    }
    _print_init_summary(summary)


@app.command()
def quickstart(
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
        init_project(Path.cwd())
    except ScaffoldError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    template_root = resolve_template_root()
    sample_sot = template_root / "sot.sample"
    if not sample_sot.exists():
        typer.echo(f"ERROR: Sample SoT not found: {sample_sot}", err=True)
        raise typer.Exit(code=1)

    errors = validate_sot(sample_sot)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)

    try:
        result = build_documents(
            sot_path=sample_sot,
            config_path=config,
            variant_id="base",
            formats=["md", "pdf", "docx"],
        )
    except (ValueError, RenderError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_quickstart_summary(result, sample_sot)


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
    _print_theme_info_summary(resolved.id, resolved.description, routes)


@variant_app.command("promote")
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


@variant_app.command("list")
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
        variants = _load_variants_from_config(config_path)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    inbox_entries = list_variant_inbox(config_path)
    inbox_payload = [_inbox_entry_payload(entry) for entry in inbox_entries]
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
        ("variants", _variants_summary_line(variants) or "none"),
        ("inbox", _inbox_summary_line(inbox_payload)),
        ("ttl_days", str(ttl_days)),
    ]
    print_summary("variant.list", rows)


@variant_app.command("inbox")
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
    try:
        entries = list_variant_inbox(config)
    except (VariantLifecycleError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_variant_inbox(entries)


@variant_app.command("keep")
def variant_keep(
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Path to variant.yaml to promote",
        ),
    ],
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
    try:
        result = keep_variant(
            variant_path=path,
            config_path=config,
            variant_id=variant_id,
            label=label,
        )
    except (VariantLifecycleError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_variant_keep_summary(result.variant_id, result.variant_path, result.status)


@variant_app.command("discard")
def variant_discard(
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Path to variant.yaml to discard",
        ),
    ],
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
    try:
        result = discard_variant(
            variant_path=path,
            config_path=config,
            confirm=yes,
        )
    except (VariantLifecycleError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_variant_discard_summary(result.variant_path, result.status)
    if not yes and result.status == "dry_run":
        raise typer.Exit(code=2)


@variant_app.command("gc")
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
    _print_variant_gc_summary(summary.expired, summary.kept_pruned, summary.status)
    if not yes and summary.status == "dry_run":
        raise typer.Exit(code=2)


@runs_app.command("gc")
def runs_gc(
    keep_latest: Annotated[
        int,
        typer.Option(
            "--keep-latest",
            min=0,
            help="Number of most recent runs to keep per variant",
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
        "kept": [_run_payload(run) for run in summary.kept],
        "invalid": [str(path) for path in summary.invalid],
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


@project_app.command("new")
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

    _print_project_new_summary(
        project_dir=result.project_dir,
        variant_id=base_variant,
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


@project_app.command("guide")
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
        base_variant = variant or resolve_default_variant(config_path)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        resolved_sot = resolve_sot_path(sot_path, config_path)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    errors = validate_sot(resolved_sot)
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
    tags_top = _top_tags(counts)
    tags_summary = _tags_summary_line(tags_top)

    try:
        if job_url:
            project_paths = create_project_from_url(
                url=job_url,
                slug=slug,
                base_variant_id=base_variant,
                config_path=config_path,
                sot_path=resolved_sot,
                store_raw=store_raw,
            )
            job_source = job_url
        else:
            project_paths = create_project_from_file(
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

    try:
        signals = _load_job_signals(project_paths.signals_path)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    raw_keywords: list[str] = []
    keywords_value = signals.get("keywords")
    if isinstance(keywords_value, list):
        raw_keywords = [item for item in keywords_value if isinstance(item, str)]
    job_keywords = _normalize_keywords(raw_keywords)
    keyword_overlap = _job_keyword_overlap(job_keywords, counts)

    try:
        variants = _load_variants_from_config(config_path)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    recommendations = _recommend_variants(variants, job_keywords, counts, base_variant)

    summary = {
        "project": {
            "project_id": project_paths.project_dir.name,
            "project_dir": str(project_paths.project_dir),
            "base_variant": base_variant,
            "job_source": job_source,
        },
        "job": {
            "keywords": job_keywords,
            "keywords_in_sot": keyword_overlap["matched"],
            "keywords_missing": keyword_overlap["missing"],
        },
        "sot": {
            "path": str(resolved_sot),
            "tags_top": tags_top,
            "tags_summary": tags_summary,
        },
        "variants": {
            "config": variants,
            "count": len(variants),
            "default": base_variant,
        },
        "recommendations": recommendations,
    }

    if get_output_mode() == OutputMode.JSON:
        typer.echo(json.dumps({"command": "project.guide", **summary}, indent=2, sort_keys=True))
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


@app.command()
def reviewpack(
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id to package for review",
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
    resolved_variant = variant or resolve_default_variant(config)
    try:
        pack = build_review_pack(
            variant_id=resolved_variant,
            config_path=config,
        )
    except ReviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    summary = {
        "out_dir": pack.out_dir,
        "docx": pack.docx_path,
        "pdf": pack.pdf_path,
        "review": pack.review_path,
        "run_id": pack.run_id,
    }
    _print_reviewpack_summary(summary)


@app.command("import-docx")
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
            help="Run id or path to locate canonical markdown",
        ),
    ] = None,
    variant: Annotated[
        str | None,
        typer.Option(
            "--variant",
            help="Variant id to resolve the latest run",
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
    try:
        result = import_docx_review(
            docx_path=docx_path,
            config_path=config,
            run=run,
            variant_id=variant,
        )
    except ReviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    summary = {
        "draft_dir": result.draft_dir,
        "patch": result.patch_path,
        "notes": result.notes_path,
        "imported_markdown": result.imported_path,
        "run_id": result.run_id,
    }
    _print_import_summary(summary)


@app.command()
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
            help="Variant id to build",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Project id or path",
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
    project_spec = None
    variant_path_override = None
    run_dir = None
    if project:
        config_path = resolve_config_path(config)
        project_dir = resolve_project_dir(project, config_path)
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
                resolved = resolve_sot_path(sot_path, config_path)
            except (FileNotFoundError, ValueError) as exc:
                typer.echo(f"ERROR: {exc}", err=True)
                raise typer.Exit(code=1) from exc
        runs_root = resolve_runs_path(config_path) / "projects" / project_spec.project_id
        runs_root.mkdir(parents=True, exist_ok=True)
        run_dir = create_run_dir(runs_root)
        try:
            resolved = prepare_project_sot(
                project_dir=project_spec.project_dir,
                sot_path=resolved,
                run_dir=run_dir,
            )
        except ProjectError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    else:
        try:
            resolved = resolve_sot_path(sot_path, config)
        except (FileNotFoundError, ValueError) as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    errors = validate_sot(resolved)
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(code=1)

    parsed_formats = _parse_formats(formats)
    try:
        result = build_documents(
            sot_path=resolved,
            config_path=config,
            variant_id=variant,
            formats=parsed_formats,
            theme=theme,
            style_preset=style_preset,
            variant_path_override=variant_path_override,
            run_dir=run_dir,
        )
    except (ValueError, RenderError) as exc:
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
        resolved_variant = variant or resolve_default_variant(config)
        variant_path = resolve_variant_path(resolved_variant, config)
        resolved = load_variant(variant_path)
        dist_dir = resolve_dist_path(config) / resolved.id
        dist_dir.mkdir(parents=True, exist_ok=True)
        pdf_engine = resolve_pdf_engine(config)
        theme_id = theme or resolved.render_theme or resolve_default_theme(config)
        preset = style_preset or resolved.render_style_preset or resolve_style_preset(config)
        theme_dir = resolve_themes_dir(config)
        theme_obj = resolve_theme(theme_dir, theme_id)
    except (FileNotFoundError, ValueError, ThemeError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    parsed_formats = _parse_formats(formats) or resolved.outputs
    filters_path = filters_dir()
    output_files: dict[str, Path] = {}
    for fmt in parsed_formats:
        output_file = output_path(dist_dir, resolved, fmt)
        try:
            plan = build_render_plan(
                output_format=fmt,
                theme=theme_obj,
                style_preset=preset,
                pdf_engine=pdf_engine,
            )
            if fmt == "html":
                plan = prepare_html_style(dist_dir, plan, theme_obj.id, preset)
            render_document(
                canonical,
                output_file,
                resolved,
                filters_path,
                fmt,
                pdf_engine,
                plan,
            )
        except RenderError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        output_files[fmt] = output_file
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
    config_path = resolve_config_path(config)
    project_spec = None
    try:
        if project:
            project_dir = resolve_project_dir(project, config_path)
            project_spec = load_project(project_dir)
            if variant:
                typer.echo("ERROR: --variant cannot be combined with --project", err=True)
                raise typer.Exit(code=2)
            if sot_path is not None:
                typer.echo("ERROR: --sot-path cannot be combined with --project", err=True)
                raise typer.Exit(code=2)
            resolved_variant_obj = load_variant(project_spec.variant_path)
            resolved_variant = resolved_variant_obj.id
            resolved = resolve_active_sot_path(project_spec.sot_path)
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

    try:
        sot_base = resolve_versioned_root(resolved)
    except SotVersionError:
        sot_base = resolved

    controller = PreviewController(
        sot_base=sot_base,
        config_path=config_path,
        variant_id=resolved_variant,
        theme_id=resolved_theme,
        style_preset=resolved_preset,
        auto_pdf=True,
        project_dir=project_spec.project_dir if project_spec else None,
    )
    host = os.environ.get("CVW_DEV_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("CVW_DEV_PORT", "8765"))
    except ValueError as exc:
        typer.echo("ERROR: CVW_DEV_PORT must be an integer", err=True)
        raise typer.Exit(code=1) from exc
    if once or os.environ.get("CVW_DEV_ONCE") == "1":
        try:
            state = controller.build_once()
        except PreviewError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        html_path = state.output_files.get("html", state.dist_dir / "cv.html")
        _print_serve_summary(
            html_path,
            str(html_path),
            False,
        )
        return

    def _on_start(url: str, html_path: Path) -> None:
        session = new_preview_session(host=host, port=port, url=url, state=controller.state())
        write_preview_session(session, config_path)
        _print_serve_summary(
            html_path,
            url,
            True,
        )

    try:
        serve_preview(controller=controller, host=host, port=port, on_start=_on_start)
    except PreviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        if exc.errno in {48, 98, 10048}:
            typer.echo(f"ERROR: {exc}", err=True)
            typer.echo(
                "HINT: preview port is already in use. Run `cvw dev stop` or set CVW_DEV_PORT.",
                err=True,
            )
            raise typer.Exit(code=1) from exc
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    finally:
        clear_preview_session(config_path)


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
    config_path = resolve_config_path(config)
    try:
        session = load_preview_session(config_path)
    except PreviewError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    ok, error = _post_preview_stop(session.url)
    if not ok:
        if force:
            _terminate_preview_process(session.pid)
        else:
            typer.echo(f"ERROR: {error}", err=True)
            raise typer.Exit(code=1)

    if not _wait_for_port_close(session.host, session.port):
        if force:
            _terminate_preview_process(session.pid)
        else:
            typer.echo("ERROR: Preview server still running", err=True)
            raise typer.Exit(code=1)

    clear_preview_session(config_path)
    print_summary(
        "dev.stop",
        [
            ("status", "stopped"),
            ("host", session.host),
            ("port", session.port),
        ],
    )


@app.command()
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
            help="Draft directory containing patch.diff",
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
        patch_path = draft / "patch.diff"
        patch_empty = patch_path.exists() and not patch_path.read_text().strip()
        apply_draft(draft_dir=draft, sot_path=sot_path)
    except ApplyError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    status = "no_changes" if patch_empty else "applied"
    _print_apply_summary(draft, patch_path, status, sot_path)


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
def sync(
    mode: Annotated[
        str | None,
        typer.Option(
            "--mode",
            help="Sync mode: pr or local",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to workbench config",
        ),
    ] = Path("config/workbench.yaml"),
    site_config: Annotated[
        Path,
        typer.Option(
            "--site-config",
            help="Path to site sync config",
        ),
    ] = Path("config/site-sync.yaml"),
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
        resolved_config = resolve_config_path(config)
        resolved_site = resolve_config_path(site_config)
        selected_mode = mode or resolve_sync_mode(resolved_config)
        result = sync_site(
            config_path=resolved_config,
            site_config_path=resolved_site,
            mode=selected_mode,
            publish_config_path=resolved_config.parent / "publish.yaml",
        )
    except (FileNotFoundError, SyncError, RenderError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_sync_summary(result)
