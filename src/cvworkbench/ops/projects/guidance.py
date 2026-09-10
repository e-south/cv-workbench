"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/guidance.py

Interpret job evidence and describe variant recommendations and proposal plans.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cvworkbench.text import normalize_tag

GUIDANCE_ALGORITHM = "tag-overlap-v1"


def guidance_catalog_inputs(variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Define the catalog fields consumed by ranking and its input provenance."""
    return [
        {
            "id": variant["id"],
            "document_type": variant["document_type"],
            "include_tags": sorted(set(variant.get("include_tags") or [])),
            "exclude_tags": sorted(set(variant.get("exclude_tags") or [])),
        }
        for variant in variants
    ]


def normalize_keywords(values: list[str]) -> list[str]:
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


def job_keyword_overlap(
    job_keywords: list[str], tag_counts: dict[str, int]
) -> dict[str, list[str]]:
    job_set = set(job_keywords)
    tag_set = set(tag_counts.keys())
    return {
        "matched": sorted(job_set & tag_set),
        "missing": sorted(job_set - tag_set),
    }


def job_signal_counts(signals: dict[str, Any], job_keywords: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    evidence = signals.get("evidence")
    if isinstance(evidence, dict):
        for keyword, spans in evidence.items():
            normalized = normalize_tag(keyword) if isinstance(keyword, str) else ""
            if not normalized:
                continue
            mentions = 0
            if isinstance(spans, list):
                mentions = sum(1 for span in spans if isinstance(span, dict))
            counts[normalized] = max(counts.get(normalized, 0), mentions)
    for keyword in job_keywords:
        counts.setdefault(keyword, 1)
    return counts


def build_job_evidence(
    text: str,
    *,
    signals: dict[str, Any],
    job_keywords: list[str],
    limit: int = 5,
) -> list[dict[str, Any]]:
    evidence = signals.get("evidence")
    if not isinstance(evidence, dict):
        return []
    signal_counts = job_signal_counts(signals, job_keywords)
    items: list[tuple[str, int, int, int]] = []
    for keyword in job_keywords:
        spans = evidence.get(keyword)
        if not isinstance(spans, list) or not spans:
            continue
        first = spans[0]
        if not isinstance(first, dict):
            continue
        start = first.get("start")
        end = first.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        items.append((keyword, signal_counts.get(keyword, 1), start, end))
    items.sort(key=lambda item: (-item[1], item[0]))

    previews: list[dict[str, Any]] = []
    for keyword, mentions, start, end in items[:limit]:
        previews.append(
            {
                "keyword": keyword,
                "mentions": mentions,
                "snippet": _excerpt_text(text, start, end),
            }
        )
    return previews


def _excerpt_text(text: str, start: int, end: int, radius: int = 48) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    snippet = " ".join(text[left:right].split())
    if left > 0:
        snippet = f"...{snippet}"
    if right < len(text):
        snippet = f"{snippet}..."
    return snippet


def _recommendation_rationale(
    *,
    include: set[str],
    include_matches: list[str],
    include_missing: list[str],
    exclude_matches: list[str],
    missing_in_sot: list[str],
    default: bool,
) -> list[str]:
    reasons: list[str] = []
    if include_matches:
        reasons.append("matched include tags: " + ", ".join(include_matches))
    elif include:
        reasons.append("no include tag matches in the job text")
    elif default:
        reasons.append("broad default fallback with no include-tag gate")
    else:
        reasons.append("broad fallback variant with no include-tag gate")
    if missing_in_sot:
        reasons.append("include tags absent from current SoT: " + ", ".join(missing_in_sot))
    if include_missing:
        reasons.append("job text does not mention: " + ", ".join(include_missing))
    if exclude_matches:
        reasons.append("blocked by exclude tags: " + ", ".join(exclude_matches))
    return reasons


def recommend_variants(
    variants: list[dict[str, Any]],
    job_keywords: list[str],
    tag_counts: dict[str, int],
    default_variant: str,
    signal_counts: dict[str, int],
) -> list[dict[str, Any]]:
    job_set = set(job_keywords)
    tag_set = set(tag_counts.keys())
    recommendations: list[dict[str, Any]] = []
    for variant in guidance_catalog_inputs(variants):
        include = set(variant.get("include_tags") or [])
        exclude = set(variant.get("exclude_tags") or [])
        include_matches = sorted(include & job_set)
        include_missing = sorted(include - job_set)
        missing_in_sot = sorted(include - tag_set)
        exclude_matches = sorted(exclude & job_set)
        include_signal_score = sum(signal_counts.get(tag, 0) for tag in include_matches)
        include_sot_score = sum(tag_counts.get(tag, 0) for tag in include_matches)
        default_bonus = 1 if not include and variant["id"] == default_variant else 0
        missing_penalty = (len(include_missing) * 2) + (len(missing_in_sot) * 3)
        exclude_penalty = len(exclude_matches) * 5
        score = (include_signal_score * 3) + include_sot_score + default_bonus
        score -= missing_penalty + exclude_penalty
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
                "score_breakdown": {
                    "job_signal": include_signal_score,
                    "sot_coverage": include_sot_score,
                    "default_bonus": default_bonus,
                    "missing_penalty": missing_penalty,
                    "exclude_penalty": exclude_penalty,
                },
                "rationale": _recommendation_rationale(
                    include=include,
                    include_matches=include_matches,
                    include_missing=include_missing,
                    exclude_matches=exclude_matches,
                    missing_in_sot=missing_in_sot,
                    default=variant["id"] == default_variant,
                ),
            }
        )
    recommendations.sort(
        key=lambda item: (
            not item["eligible"],
            -item["score"],
            -len(item["include_matches"]),
            not item["default"],
            item["variant_id"],
        )
    )
    for idx, item in enumerate(recommendations, start=1):
        item["rank"] = idx
    return recommendations


def build_proposal_plan(
    *,
    project_id: str,
    project_dir: Path,
    job_keywords: list[str],
    keyword_overlap: dict[str, list[str]],
    recommendations: list[dict[str, Any]],
    job_evidence: list[dict[str, Any]],
    requested_variant: str,
    applied_variant: str,
    selection_mode: str,
) -> dict[str, Any]:
    selected = recommendations[0] if recommendations else None
    selected_variant = selected["variant_id"] if selected is not None else None
    status = (
        "blocked"
        if selected is None or not selected["eligible"]
        else "targeted"
        if selected["include_matches"]
        else "fallback"
    )
    if selected is None:
        summary = "No variants are available."
    elif selected["rationale"]:
        summary = selected["rationale"][0]
    else:
        summary = "Use the proposal variant as the starting point."

    steps = [
        f"Inspect `project show {project_id}` and preview the proposal variant.",
        "Capture supported SoT edits as project-ops before exporting review artifacts.",
        "Build md,pdf,docx once the proposal text matches the intended scope.",
    ]
    if keyword_overlap["missing"]:
        steps.insert(
            1,
            "Review missing job signals against your experience; add only supported details.",
        )

    return {
        "path": str(project_dir / "job" / "proposal-plan.json"),
        "requested_variant": requested_variant,
        "selected_variant": selected_variant,
        "applied_variant": applied_variant,
        "selection_mode": selection_mode,
        "status": status,
        "summary": summary,
        "job_keywords": job_keywords,
        "job_keywords_missing_in_sot": keyword_overlap["missing"],
        "job_evidence": job_evidence,
        "recommendation": selected,
        "steps": steps,
    }
