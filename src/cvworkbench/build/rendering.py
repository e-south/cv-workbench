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
) -> None:
    pandoc_path = _which("pandoc")
    if pandoc_path is None:
        raise RenderError("pandoc is required but was not found in PATH")

    if output_format == "pdf" and pdf_engine:
        if _which(pdf_engine) is None:
            raise RenderError(f"PDF engine '{pdf_engine}' was not found in PATH")

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
    pandoc_format = _map_format(output_format)
    args = [
        pandoc_path,
        "--from",
        MARKDOWN_INPUT,
        "--to",
        pandoc_format,
        "--output",
        str(output_path),
    ]

    if output_format == "pdf" and pdf_engine:
        args.extend(["--pdf-engine", pdf_engine])

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
    return output_format
