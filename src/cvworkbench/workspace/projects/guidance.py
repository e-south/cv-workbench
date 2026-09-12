"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/projects/guidance.py

Explain saved project guidance and summarize recommendation text.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from typing import Any

from cvworkbench.ops.projects import GuidanceInputCheck, ProjectArtifactCheck, ProjectProposalIssue
from cvworkbench.variants import validate_variant_id

_INPUT_LABELS = {
    "extracted_text": "extracted text",
    "signals": "signals",
    "source_tags": "source tags",
    "variant_catalog": "variant catalog",
    "default_variant": "default variant",
}


def proposal_input_warning(issues: tuple[ProjectProposalIssue, ...]) -> str | None:
    if not issues:
        return None
    return " ".join(issue.error for issue in issues) + (
        " Restore valid proposal files before previewing, building, applying, or keeping the proposal."
        " Retained job context and run history remain inspectable."
    )


def guidance_input_context(check: GuidanceInputCheck) -> dict[str, Any]:
    context: dict[str, Any] = {
        "guidance_inputs": {
            "state": check.state,
            "changed": list(check.changed),
            "unavailable": list(check.unavailable),
            "errors": list(check.errors),
        },
        "guidance_input_status": {
            "matches_inputs": "match saved inputs",
            "changed": "changed",
            "unverifiable": "unverifiable",
        }[check.state],
    }
    if check.state != "matches_inputs":
        messages = []
        if check.changed:
            messages.append(
                "Saved guidance inputs changed: "
                + ", ".join(_INPUT_LABELS[key] for key in check.changed)
                + "."
            )
        if check.unavailable:
            messages.append(
                "Could not compare: "
                + ", ".join(_INPUT_LABELS[key] for key in check.unavailable)
                + "."
            )
        messages.extend(check.errors)
        messages.append("Review the recommendations before using them.")
        context["guidance_input_warning"] = " ".join(messages)
    return context


def project_artifact_context(
    checks: tuple[ProjectArtifactCheck, ...], *, include_details: bool = False
) -> dict[str, Any]:
    problems = [check for check in checks if check.state != "matches_record"]
    context: dict[str, Any] = {
        "job_artifact_status": "not checked"
        if not checks
        else "need review"
        if problems
        else "match saved record"
    }
    if problems:
        states = ", ".join(f"{_INPUT_LABELS[check.name]} ({check.state})" for check in problems)
        context["job_artifact_warning"] = (
            f"Stored job context needs review: {states}. "
            "Review the source job description before relying on saved guidance."
        )
    if include_details:
        context["job_artifacts"] = {
            check.name: {
                "path": str(check.path),
                "state": check.state,
                "recorded_sha256": check.recorded_sha256,
                "observed_sha256": check.observed_sha256,
                "error": check.error,
            }
            for check in checks
        }
    return context


def proposal_plan_selection_warning(
    plan: dict[str, Any] | None, current_base_variant: str
) -> str | None:
    if plan is None:
        return None
    recorded = plan.get("applied_variant")
    try:
        validate_variant_id(recorded)
    except ValueError:
        return (
            "Saved guidance does not identify an applied variant. "
            "Compare its recommendations with the current proposal before using them."
        )
    if recorded != current_base_variant:
        return (
            f"Saved guidance was recorded for '{recorded}'; "
            f"the current base variant is '{current_base_variant}'. "
            "Review its recommendations before using them."
        )
    return None


def recommendations_summary_line(recommendations: list[dict[str, Any]], limit: int = 5) -> str:
    if not recommendations:
        return "none"
    lines: list[str] = []
    for item in recommendations[:limit]:
        parts = [item["variant_id"], f"score={item['score']}"]
        if item.get("default"):
            parts.append("default")
        if item.get("include_matches"):
            parts.append("match=" + ",".join(item["include_matches"]))
        if item.get("rationale"):
            parts.append("why=" + item["rationale"][0])
        if item.get("exclude_matches"):
            parts.append("exclude=" + ",".join(item["exclude_matches"]))
        if item.get("missing_in_sot"):
            parts.append("missing_sot=" + ",".join(item["missing_in_sot"]))
        lines.append(" | ".join(parts))
    return "\n".join(lines)
