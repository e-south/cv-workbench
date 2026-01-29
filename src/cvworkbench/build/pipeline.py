"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/pipeline.py

Builds document outputs from Source of Truth data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import datetime, timezone
from pathlib import Path

from cvworkbench.config import (
    resolve_default_variant,
    resolve_dist_path,
    resolve_pdf_engine,
    resolve_runs_path,
    resolve_variant_path,
)
from cvworkbench.build.manifest import build_manifest, write_manifest
from cvworkbench.build.markdown import build_markdown
from cvworkbench.build.paths import filters_dir, output_path
from cvworkbench.build.rendering import render_document
from cvworkbench.build.resume import build_resume, write_resume
from cvworkbench.build.selection import build_selection
from cvworkbench.inputs.sot import load_sot
from cvworkbench.variants import Variant, load_variant


@dataclass(frozen=True)
class BuildResult:
    variant: Variant
    formats: list[str]
    canonical_path: Path
    dist_dir: Path
    run_dir: Path


def build_documents(
    *,
    sot_path: Path,
    config_path: Path,
    variant_id: str | None,
    formats: list[str] | None,
) -> BuildResult:
    resolved_variant = variant_id or resolve_default_variant(config_path)
    variant_path = resolve_variant_path(resolved_variant, config_path)
    variant = load_variant(variant_path)
    selected_formats = formats or variant.outputs

    sot = load_sot(sot_path)
    markdown = build_markdown(sot, variant)
    selection = build_selection(sot, variant)

    run_dir = _create_run_dir(resolve_runs_path(config_path))
    canonical_path = run_dir / "canonical.md"
    canonical_path.write_text(markdown)
    resume_payload = build_resume(sot)
    resume_path = run_dir / "resume.json"
    write_resume(resume_path, resume_payload)
    selection_path = run_dir / "selection.json"
    selection_path.write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n")

    dist_dir = resolve_dist_path(config_path) / variant.id
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "selection.json").write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n")

    filters_path = filters_dir()
    pdf_engine = resolve_pdf_engine(config_path)
    output_paths: dict[str, Path] = {}

    for fmt in selected_formats:
        output_file = output_path(dist_dir, variant, fmt)
        render_document(
            canonical_path,
            output_file,
            variant,
            filters_path,
            fmt,
            pdf_engine,
        )
        output_paths[fmt] = output_file

    manifest = build_manifest(
        variant=variant,
        variant_path=variant_path,
        sot_path=sot_path,
        formats=selected_formats,
        output_paths=output_paths,
        resume_path=resume_path,
        pdf_engine=pdf_engine,
        repo_root=config_path.parent.parent,
    )
    write_manifest(dist_dir / "manifest.json", manifest)
    write_manifest(run_dir / "manifest.json", manifest)

    return BuildResult(
        variant=variant,
        formats=selected_formats,
        canonical_path=canonical_path,
        dist_dir=dist_dir,
        run_dir=run_dir,
    )


def _create_run_dir(runs_root: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    run_dir = runs_root / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
