"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/pipeline.py

Builds document outputs from Source of Truth data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import copy
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cvworkbench.build.manifest import build_manifest, write_manifest
from cvworkbench.build.markdown import build_markdown
from cvworkbench.build.paths import filters_dir, output_path
from cvworkbench.build.rendering import render_document
from cvworkbench.build.resume import build_resume, write_resume
from cvworkbench.build.selection import build_selection
from cvworkbench.build.styles import prepare_html_style
from cvworkbench.config import (
    resolve_default_theme,
    resolve_default_variant,
    resolve_dist_path,
    resolve_pdf_engine,
    resolve_runs_path,
    resolve_style_preset,
    resolve_themes_dir,
    resolve_variant_path,
)
from cvworkbench.inputs.sot import load_sot
from cvworkbench.themes import ThemeError, build_render_plan, hash_theme, resolve_theme
from cvworkbench.variants import Variant, load_variant


@dataclass(frozen=True)
class BuildResult:
    variant: Variant
    formats: list[str]
    canonical_path: Path
    dist_dir: Path
    run_dir: Path
    theme_id: str | None
    style_preset: str | None


def build_documents(
    *,
    sot_path: Path,
    config_path: Path,
    variant_id: str | None,
    formats: list[str] | None,
    theme: str | None = None,
    style_preset: str | None = None,
    variant_path_override: Path | None = None,
    run_dir: Path | None = None,
    dist_dir: Path | None = None,
) -> BuildResult:
    if variant_path_override is not None:
        variant_path = variant_path_override
        variant = load_variant(variant_path)
        resolved_variant = variant.id
    else:
        resolved_variant = variant_id or resolve_default_variant(config_path)
        variant_path = resolve_variant_path(resolved_variant, config_path)
        variant = load_variant(variant_path)
    selected_formats = formats or variant.outputs

    sot = load_sot(sot_path)
    markdown = build_markdown(sot, variant)
    selection = build_selection(sot, variant)

    run_dir = _ensure_run_dir(resolve_runs_path(config_path), run_dir)
    canonical_path = run_dir / "canonical.md"
    canonical_path.write_text(markdown)
    resume_payload = build_resume(sot)
    resume_path = run_dir / "resume.json"
    write_resume(resume_path, resume_payload)
    selection_path = run_dir / "selection.json"
    selection_path.write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n")

    dist_dir = dist_dir or (resolve_dist_path(config_path) / variant.id)
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "selection.json").write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n")

    filters_path = filters_dir()
    pdf_engine = resolve_pdf_engine(config_path)
    theme_id = theme or variant.render_theme or resolve_default_theme(config_path)
    preset = style_preset or variant.render_style_preset or resolve_style_preset(config_path)
    theme_root = resolve_themes_dir(config_path)
    try:
        theme_obj = resolve_theme(theme_root, theme_id)
    except ThemeError as exc:
        raise ValueError(str(exc)) from exc

    output_paths: dict[str, Path] = {}
    render_details: dict[str, dict[str, str | None | list[str]]] = {}
    theme_hash = hash_theme(theme_obj)

    for fmt in selected_formats:
        output_file = output_path(dist_dir, variant, fmt)
        plan = build_render_plan(
            output_format=fmt,
            theme=theme_obj,
            style_preset=preset,
            pdf_engine=pdf_engine,
        )
        if fmt == "html":
            plan = prepare_html_style(dist_dir, plan, theme_obj.id, preset)
        render_document(
            canonical_path,
            output_file,
            variant,
            filters_path,
            fmt,
            pdf_engine,
            plan,
        )
        run_output = run_dir / output_file.name
        if output_file.resolve() != run_output.resolve():
            shutil.copy2(output_file, run_output)
        output_paths[fmt] = output_file
        render_details[fmt] = {
            "to": plan.to,
            "template": str(plan.template) if plan.template else None,
            "pdf_engine": plan.pdf_engine,
            "defaults": [str(path) for path in plan.defaults],
            "style_path": str(plan.style_path) if plan.style_path else None,
            "style_hash": plan.style_hash,
        }

    dist_manifest = build_manifest(
        variant=variant,
        variant_path=variant_path,
        sot_path=sot_path,
        formats=selected_formats,
        output_paths=output_paths,
        resume_path=resume_path,
        pdf_engine=pdf_engine,
        repo_root=config_path.parent.parent,
        render={
            "theme": theme_obj.id,
            "theme_hash": theme_hash,
            "style_preset": preset,
            "formats": render_details,
        },
    )
    write_manifest(dist_dir / "manifest.json", dist_manifest)

    # Reuse the deterministic manifest payload so build metadata is computed once.
    run_manifest = copy.deepcopy(dist_manifest)
    run_manifest["created_at"] = datetime.now(timezone.utc).isoformat()
    write_manifest(run_dir / "manifest.json", run_manifest)

    return BuildResult(
        variant=variant,
        formats=selected_formats,
        canonical_path=canonical_path,
        dist_dir=dist_dir,
        run_dir=run_dir,
        theme_id=theme_obj.id,
        style_preset=preset,
    )


def create_run_dir(runs_root: Path) -> Path:
    base_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    runs_root.mkdir(parents=True, exist_ok=True)

    for suffix in range(0, 1000):
        name = base_timestamp if suffix == 0 else f"{base_timestamp}-{suffix:02d}"
        run_dir = runs_root / name
        try:
            run_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            continue
        return run_dir

    raise RuntimeError(f"Could not allocate unique run directory for timestamp: {base_timestamp}")


def _ensure_run_dir(runs_root: Path, run_dir: Path | None) -> Path:
    if run_dir is None:
        return create_run_dir(runs_root)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
