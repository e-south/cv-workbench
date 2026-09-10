"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/workflow.py

Coordinate project guidance with input preflight and failed-workspace recovery.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cvworkbench.config import (
    ConfigSource,
    read_config,
    resolve_default_variant,
    resolve_sot_path,
    resolve_variant_path,
)
from cvworkbench.ingestion.registry import RegistryError
from cvworkbench.inputs.sot import load_sot
from cvworkbench.inputs.tags import extract_tags, tag_counts
from cvworkbench.inputs.validation import validate_sot
from cvworkbench.ops.projects.artifacts import capture_guidance_job_inputs
from cvworkbench.ops.projects.creation import (
    create_project_from_file,
    create_project_from_url,
    discard_project_workspace,
    retarget_project_variant,
)
from cvworkbench.ops.projects.guidance import (
    build_job_evidence,
    build_proposal_plan,
    job_keyword_overlap,
    job_signal_counts,
    normalize_keywords,
    recommend_variants,
)
from cvworkbench.ops.projects.provenance import guidance_input_provenance
from cvworkbench.ops.projects.records import ProjectError, ProjectPaths
from cvworkbench.variants import load_variant, load_variants_from_config


class ProjectGuideError(ProjectError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True)
class ProjectGuideResult:
    paths: ProjectPaths
    config_path: Path
    sot_path: Path
    job_source: str
    applied_variant_id: str
    proposal_variant_id: str
    source_tag_counts: dict[str, int]
    job: dict[str, Any]
    variant_catalog: list[dict[str, Any]]
    default_variant_id: str
    recommendations: list[dict[str, Any]]
    proposal_plan: dict[str, Any]


def guide_project(
    *,
    config_path: ConfigSource,
    job_url: str | None = None,
    job_file: Path | None = None,
    slug: str | None = None,
    variant_id: str | None = None,
    sot_path: Path | None = None,
    store_raw: bool = False,
) -> ProjectGuideResult:
    if (job_url is None) == (job_file is None):
        raise ProjectGuideError(["Provide exactly one of --job-url or --job-file"])
    if job_url is not None and not job_url.strip():
        raise ProjectGuideError(["Job URL is required"])
    if job_file is not None:
        if not job_file.exists():
            raise ProjectGuideError([f"Job file not found: {job_file}"])
        if not job_file.is_file():
            raise ProjectGuideError([f"Job file must be a regular file: {job_file}"])

    try:
        configuration = read_config(config_path)
        config_path = configuration.path
        default_variant = resolve_default_variant(configuration)
        requested_variant = variant_id if variant_id is not None else default_variant
        resolved_sot = resolve_sot_path(sot_path, configuration)
        errors = validate_sot(resolved_sot)
        if errors:
            raise ProjectGuideError(errors)
        source = load_sot(resolved_sot)
        counts = tag_counts(extract_tags(source))
        variants = load_variants_from_config(config_path)
        if not resolve_variant_path(requested_variant, configuration).is_file():
            raise ProjectGuideError([f"Base variant not found: {requested_variant}"])

        if job_url is not None:
            paths = create_project_from_url(
                url=job_url,
                slug=slug,
                base_variant_id=requested_variant,
                config_path=configuration,
                sot_path=resolved_sot,
                store_raw=store_raw,
            )
            job_source = job_url
        else:
            assert job_file is not None
            paths = create_project_from_file(
                job_path=job_file,
                slug=slug,
                base_variant_id=requested_variant,
                config_path=configuration,
                sot_path=resolved_sot,
                store_raw=store_raw,
            )
            job_source = str(job_file)
    except ProjectGuideError:
        raise
    except (ProjectError, RegistryError, OSError, ValueError, yaml.YAMLError) as exc:
        raise ProjectGuideError([str(exc)]) from exc

    stage = "project guidance"
    try:
        job_inputs = capture_guidance_job_inputs(paths)
        signals = job_inputs.signals
        provenance = guidance_input_provenance(
            job_inputs, source_tags=counts, variants=variants, default_variant=default_variant
        )
        keywords_value = signals.get("keywords")
        raw_keywords = (
            [item for item in keywords_value if isinstance(item, str)]
            if isinstance(keywords_value, list)
            else []
        )
        job_keywords = normalize_keywords(raw_keywords)
        overlap = job_keyword_overlap(job_keywords, counts)
        signal_counts = job_signal_counts(signals, job_keywords)
        job_evidence = build_job_evidence(
            job_inputs.text, signals=signals, job_keywords=job_keywords
        )
        recommendations = recommend_variants(
            variants, job_keywords, counts, default_variant, signal_counts
        )
        applied_variant = requested_variant
        selection_mode = "explicit" if variant_id is not None else "requested"
        selected = recommendations[0] if recommendations else None
        if variant_id is None and selected is not None and selected["eligible"]:
            recommended_variant = selected["variant_id"]
            if recommended_variant != requested_variant:
                stage = "guide retargeting"
                retarget_project_variant(
                    project_dir=paths.project_dir,
                    base_variant_id=recommended_variant,
                    config_path=configuration,
                )
                stage = "project guidance"
            applied_variant = recommended_variant
            selection_mode = "recommended"
        plan = build_proposal_plan(
            project_id=paths.project_dir.name,
            project_dir=paths.project_dir,
            job_keywords=job_keywords,
            keyword_overlap=overlap,
            recommendations=recommendations,
            job_evidence=job_evidence,
            requested_variant=requested_variant,
            applied_variant=applied_variant,
            selection_mode=selection_mode,
        )
        plan["provenance"] = provenance
        Path(plan["path"]).write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
        return ProjectGuideResult(
            paths=paths,
            config_path=config_path,
            sot_path=resolved_sot,
            job_source=job_source,
            applied_variant_id=applied_variant,
            proposal_variant_id=load_variant(paths.variant_path).id,
            source_tag_counts=counts,
            job={
                "keywords": job_keywords,
                "keywords_in_sot": overlap["matched"],
                "keywords_missing": overlap["missing"],
                "evidence": job_evidence,
            },
            variant_catalog=variants,
            default_variant_id=default_variant,
            recommendations=recommendations,
            proposal_plan=plan,
        )
    except BaseException as exc:
        errors = [str(exc)]
        try:
            discard_project_workspace(project_dir=paths.project_dir, config_path=configuration)
        except Exception as rollback_exc:
            errors.append(
                f"Failed to roll back the project workspace after {stage} failed: {rollback_exc}"
            )
        if not isinstance(exc, Exception):
            for error in errors[1:]:
                exc.add_note(error)
            raise
        raise ProjectGuideError(errors) from exc
