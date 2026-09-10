"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/planning.py

Resolve build content, configuration, and render choices before artifact writes.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cvworkbench.build.formats import normalize_output_formats
from cvworkbench.build.markdown import build_markdown
from cvworkbench.build.paths import filters_dir
from cvworkbench.build.rendering import resolve_filter_paths
from cvworkbench.build.resume import build_resume
from cvworkbench.build.selection import build_selection
from cvworkbench.config import (
    ConfigSnapshot,
    ConfigSource,
    read_config,
    resolve_default_theme,
    resolve_default_variant,
    resolve_pdf_engine,
    resolve_style_preset,
    resolve_themes_dir,
    resolve_variant_path,
)
from cvworkbench.inputs.sot import load_sot
from cvworkbench.themes import (
    RenderPlan,
    Theme,
    ThemeError,
    build_render_plan,
    hash_theme,
    resolve_theme,
)
from cvworkbench.variants import Variant, load_variant


@dataclass(frozen=True)
class BuildPlan:
    configuration: ConfigSnapshot
    sot_path: Path
    variant_path: Path
    variant: Variant
    formats: list[str]
    markdown: str = field(repr=False)
    selection_payload: str = field(repr=False)
    resume_payload: dict[str, Any] = field(repr=False)
    filters_path: Path
    filter_paths: tuple[Path, ...]
    pdf_engine: str | None
    theme: Theme
    theme_hash: str
    style_preset: str | None
    render_plans: dict[str, RenderPlan]


def plan_build(
    *,
    sot_path: Path,
    config_path: ConfigSource,
    variant_id: str | None,
    formats: list[str] | None,
    theme: str | None = None,
    style_preset: str | None = None,
    variant_path_override: Path | None = None,
) -> BuildPlan:
    """Prepare a request-local build plan without allocating runs or writing outputs."""
    configuration = read_config(config_path)
    variant_path = variant_path_override
    if variant_path is None:
        selected_id = variant_id or resolve_default_variant(configuration)
        variant_path = resolve_variant_path(selected_id, configuration)
    variant = load_variant(variant_path)
    selected_formats = normalize_output_formats(formats if formats is not None else variant.outputs)
    if not selected_formats:
        raise ValueError("No output formats selected")

    sot = load_sot(sot_path)
    markdown = build_markdown(sot, variant)
    selection_payload = json.dumps(build_selection(sot, variant), indent=2, sort_keys=True) + "\n"
    resume_payload = build_resume(sot)
    filters_path = filters_dir()
    filter_paths = resolve_filter_paths(filters_path)
    pdf_engine = resolve_pdf_engine(configuration)
    theme_id = theme or variant.render_theme or resolve_default_theme(configuration)
    preset = style_preset or variant.render_style_preset or resolve_style_preset(configuration)
    try:
        theme_obj = resolve_theme(resolve_themes_dir(configuration), theme_id)
    except ThemeError as exc:
        raise ValueError(str(exc)) from exc
    render_plans = {
        fmt: build_render_plan(
            output_format=fmt, theme=theme_obj, style_preset=preset, pdf_engine=pdf_engine
        )
        for fmt in selected_formats
    }
    return BuildPlan(
        configuration=configuration,
        sot_path=sot_path,
        variant_path=variant_path,
        variant=variant,
        formats=selected_formats,
        markdown=markdown,
        selection_payload=selection_payload,
        resume_payload=resume_payload,
        filters_path=filters_path,
        filter_paths=filter_paths,
        pdf_engine=pdf_engine,
        theme=theme_obj,
        theme_hash=hash_theme(theme_obj),
        style_preset=preset,
        render_plans=render_plans,
    )
