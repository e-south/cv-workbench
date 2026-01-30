"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/rendering.py

Renders markdown into target document formats using Pandoc.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from cvworkbench.themes import RenderPlan
from cvworkbench.variants import Variant

MARKDOWN_INPUT = "markdown+fenced_divs"


class RenderError(RuntimeError):
    pass


def render_document(
    input_path: Path,
    output_path: Path,
    variant: Variant,
    filters_dir: Path,
    output_format: str,
    pdf_engine: str | None,
    render_plan: RenderPlan | None = None,
) -> None:
    pandoc_path = _which("pandoc")
    if pandoc_path is None:
        raise RenderError("pandoc is required but was not found in PATH")

    resolved_plan = render_plan or _default_plan(output_format, pdf_engine)
    if output_format == "pdf" and resolved_plan.pdf_engine:
        if _which(resolved_plan.pdf_engine) is None:
            raise RenderError(f"PDF engine '{resolved_plan.pdf_engine}' was not found in PATH")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata = {
        "include_tags": variant.include_tags,
        "exclude_tags": variant.exclude_tags,
    }
    if variant.max_bullets_per_role is not None:
        metadata["max_bullets_per_role"] = variant.max_bullets_per_role

    filter_paths = [
        filters_dir / "select.lua",
        filters_dir / "author_roles.lua",
        filters_dir / "limits.lua",
    ]
    args = [
        pandoc_path,
        "--from",
        MARKDOWN_INPUT,
        "--to",
        resolved_plan.to,
        "--output",
        str(output_path),
    ]

    if output_format == "pdf" and resolved_plan.pdf_engine:
        args.extend(["--pdf-engine", resolved_plan.pdf_engine])

    if resolved_plan.template is not None:
        args.extend(["--template", str(resolved_plan.template)])

    for defaults_path in resolved_plan.defaults:
        args.extend(["--defaults", str(defaults_path)])

    if resolved_plan.style_path is not None and resolved_plan.style_kind:
        if resolved_plan.style_kind == "css":
            args.extend(["--css", str(resolved_plan.style_path)])
        elif resolved_plan.style_kind == "header":
            args.extend(["--include-in-header", str(resolved_plan.style_path)])

    for filter_path in filter_paths:
        if filter_path.exists():
            args.extend(["--lua-filter", str(filter_path)])

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as handle:
        for key, value in metadata.items():
            handle.write(f"{key}:\n")
            if isinstance(value, list):
                for item in value:
                    handle.write(f"  - {item}\n")
            else:
                handle.write(f"  {value}\n")
        metadata_path = Path(handle.name)

    args.extend(["--metadata-file", str(metadata_path), str(input_path)])

    try:
        _run(args)
    finally:
        metadata_path.unlink(missing_ok=True)


def _run(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RenderError(message or "Pandoc failed")


def _which(command: str) -> str | None:
    result = subprocess.run(
        ["/usr/bin/which", command], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _map_format(output_format: str) -> str:
    if output_format == "md":
        return "markdown"
    if output_format == "pdf":
        return "latex"
    if output_format == "html":
        return "html5"
    return output_format


def _default_plan(output_format: str, pdf_engine: str | None) -> RenderPlan:
    return RenderPlan(
        output_format=output_format,
        to=_map_format(output_format),
        template=None,
        pdf_engine=pdf_engine if output_format == "pdf" else None,
        defaults=[],
        style_path=None,
        style_kind=None,
        theme_id=None,
        theme_hash=None,
        style_hash=None,
    )
