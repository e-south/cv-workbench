"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/pipeline.py

Builds document outputs from Source of Truth data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cvworkbench.config import (
    resolve_default_variant,
    resolve_dist_path,
    resolve_pdf_engine,
    resolve_runs_path,
    resolve_variant_path,
)
from cvworkbench.markdown import build_markdown
from cvworkbench.rendering import render_document
from cvworkbench.sot import load_sot
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

    run_dir = _create_run_dir(resolve_runs_path(config_path))
    canonical_path = run_dir / "canonical.md"
    canonical_path.write_text(markdown)

    dist_dir = resolve_dist_path(config_path) / variant.id
    dist_dir.mkdir(parents=True, exist_ok=True)

    filters_dir = _filters_dir()
    pdf_engine = resolve_pdf_engine(config_path)

    for fmt in selected_formats:
        output_path = _output_path(dist_dir, variant, fmt)
        render_document(
            canonical_path,
            output_path,
            variant,
            filters_dir,
            fmt,
            pdf_engine,
        )

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


def _output_path(dist_dir: Path, variant: Variant, fmt: str) -> Path:
    extension = fmt
    if fmt == "md":
        extension = "md"
    filename = f"{variant.output_name}.{extension}"
    return dist_dir / filename


def _filters_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "build" / "filters"
