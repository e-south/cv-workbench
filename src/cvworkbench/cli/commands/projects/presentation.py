"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/cli/commands/projects/presentation.py

Present project command payloads, proposal plans, and terminal summaries.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cvworkbench.cli.output import print_summary
from cvworkbench.workspace.commands import shell_command
from cvworkbench.workspace.project_guidance import (
    recommendations_summary_line,
)
from cvworkbench.workspace.projects import (
    project_commands,
)


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
        ("job_files", summary["job_artifact_status"]),
        ("next_step", summary["commands"]["preview"]),
        ("build_step", summary["commands"]["build"]),
        ("review_status", summary["review"]["status"]),
        ("review_step", summary["review"]["next_command"]),
        ("apply_step", summary["commands"]["apply"]),
        ("keep_step", summary["commands"]["keep"]),
        ("discard_step", summary["commands"]["discard"]),
    ]
    rows.extend(_proposal_plan_summary_rows(summary.get("proposal_plan")))
    if "guidance_input_status" in summary:
        rows.append(("guidance_inputs", summary["guidance_input_status"]))
    if "guidance_input_warning" in summary:
        rows.append(("guidance_input_warning", summary["guidance_input_warning"]))
    if summary["patch"]["render_warning"]:
        rows.append(("patch_note", summary["patch"]["render_warning"]))
    if summary["review"]["run_id"]:
        rows.append(("review_run", summary["review"]["run_id"]))
    if "proposal_plan_error" in summary:
        rows.append(("proposal_plan_error", summary["proposal_plan_error"]))
    if "proposal_plan_warning" in summary:
        rows.append(("proposal_plan_warning", summary["proposal_plan_warning"]))
    if "job_artifact_warning" in summary:
        rows.append(("job_artifact_warning", summary["job_artifact_warning"]))
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
