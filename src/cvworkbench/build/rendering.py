"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/rendering.py

Renders markdown into target document formats using Pandoc.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Sequence

from cvworkbench.build.docx import validate_docx
from cvworkbench.themes import RenderPlan
from cvworkbench.variants import Variant

MARKDOWN_INPUT = "markdown+fenced_divs"


class RenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderRequest:
    input_path: Path
    output_path: Path
    variant: Variant
    filters_dir: Path
    output_format: str
    pdf_engine: str | None
    render_plan: RenderPlan | None = None


def render_document(
    input_path: Path,
    output_path: Path,
    variant: Variant,
    filters_dir: Path,
    output_format: str,
    pdf_engine: str | None,
    render_plan: RenderPlan | None = None,
    *,
    pandoc_path: str | None = None,
    filter_paths: Sequence[Path] | None = None,
) -> None:
    """Render one document, replacing its destination only after successful completion."""
    render_documents(
        [
            RenderRequest(
                input_path,
                output_path,
                variant,
                filters_dir,
                output_format,
                pdf_engine,
                render_plan,
            )
        ],
        pandoc_path=pandoc_path,
        filter_paths=filter_paths,
    )


def _render_document(
    input_path: Path,
    output_path: Path,
    variant: Variant,
    filters_dir: Path,
    output_format: str,
    pdf_engine: str | None,
    render_plan: RenderPlan | None = None,
    *,
    pandoc_path: str | None = None,
    filter_paths: Sequence[Path] | None = None,
) -> None:
    resolved_pandoc_path = pandoc_path or _which("pandoc")
    if resolved_pandoc_path is None:
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
    if variant.render_page_break_before:
        metadata["cvw-page-break-before"] = variant.render_page_break_before

    resolved_filter_paths = (
        tuple(filter_paths) if filter_paths is not None else resolve_filter_paths(filters_dir)
    )
    args = [
        resolved_pandoc_path,
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
    if resolved_plan.reference_doc is not None:
        args.extend(["--reference-doc", str(resolved_plan.reference_doc)])

    for defaults_path in resolved_plan.defaults:
        args.extend(["--defaults", str(defaults_path)])

    if resolved_plan.style_path is not None and resolved_plan.style_kind:
        if resolved_plan.style_kind == "css":
            args.extend(["--css", str(resolved_plan.style_path)])
        elif resolved_plan.style_kind == "header":
            args.extend(["--include-in-header", str(resolved_plan.style_path)])

    for filter_path in resolved_filter_paths:
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
        if output_format == "docx":
            try:
                validate_docx(output_path)
            except ValueError as error:
                raise RenderError(str(error)) from error
    finally:
        metadata_path.unlink(missing_ok=True)


def render_documents(
    requests: Sequence[RenderRequest],
    *,
    pandoc_path: str | None = None,
    filter_paths: Sequence[Path] | None = None,
    max_workers: int | None = None,
    after_each_success: Callable[[RenderRequest], None] | None = None,
) -> None:
    """Stage renders and publish each completed output in request order."""
    request_list = tuple(requests)
    if not request_list:
        return
    destinations = [request.output_path.resolve() for request in request_list]
    if len(set(destinations)) != len(destinations):
        raise RenderError("Render requests must have distinct output paths")

    resolved_pandoc_path = pandoc_path or _which("pandoc")
    if resolved_pandoc_path is None:
        raise RenderError("pandoc is required but was not found in PATH")
    resolved_filter_paths = tuple(filter_paths) if filter_paths is not None else None

    worker_limit = max_workers or min(len(request_list), max(os.cpu_count() or 1, 1))
    with ExitStack() as staged_outputs:
        scheduled_requests = []
        for request in request_list:
            request.output_path.parent.mkdir(parents=True, exist_ok=True)
            staging_dir = staged_outputs.enter_context(
                tempfile.TemporaryDirectory(
                    prefix=f".{request.output_path.stem}.", dir=request.output_path.parent
                )
            )
            temp_output_path = Path(staging_dir) / request.output_path.name
            scheduled_requests.append(_ScheduledRenderRequest(request, temp_output_path))

        if worker_limit <= 1 or len(request_list) == 1:
            for scheduled in scheduled_requests:
                _render_request(
                    scheduled.request,
                    pandoc_path=resolved_pandoc_path,
                    filter_paths=resolved_filter_paths,
                    output_path=scheduled.temp_output_path,
                )
                _publish_output(scheduled, after_each_success)
            return

        with ThreadPoolExecutor(max_workers=worker_limit) as executor:
            futures = [
                executor.submit(
                    _render_request,
                    scheduled.request,
                    pandoc_path=resolved_pandoc_path,
                    filter_paths=resolved_filter_paths,
                    output_path=scheduled.temp_output_path,
                )
                for scheduled in scheduled_requests
            ]
            for scheduled, future in zip(scheduled_requests, futures, strict=True):
                future.result()
                _publish_output(scheduled, after_each_success)


def _run(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RenderError(message or "Pandoc failed")


def resolve_filter_paths(filters_dir: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in (
            filters_dir / "select.lua",
            filters_dir / "author_roles.lua",
            filters_dir / "limits.lua",
            filters_dir / "teaching_layout.lua",
            filters_dir / "presentation.lua",
            filters_dir / "entry_structure.lua",
            filters_dir / "page_breaks.lua",
        )
        if path.exists()
    )


@lru_cache(maxsize=None)
def _which(command: str) -> str | None:
    result = subprocess.run(
        ["/usr/bin/which", command], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


@dataclass(frozen=True)
class _ScheduledRenderRequest:
    request: RenderRequest
    temp_output_path: Path


def _publish_output(
    scheduled: _ScheduledRenderRequest,
    after_each_success: Callable[[RenderRequest], None] | None,
) -> None:
    scheduled.temp_output_path.replace(scheduled.request.output_path)
    if after_each_success is not None:
        after_each_success(scheduled.request)


def _render_request(
    request: RenderRequest,
    *,
    pandoc_path: str,
    filter_paths: Sequence[Path] | None,
    output_path: Path,
) -> None:
    _render_document(
        request.input_path,
        output_path,
        request.variant,
        request.filters_dir,
        request.output_format,
        request.pdf_engine,
        request.render_plan,
        pandoc_path=pandoc_path,
        filter_paths=filter_paths,
    )


def _map_format(output_format: str) -> str:
    if output_format == "md":
        return "markdown"
    if output_format == "pdf":
        return "latex"
    if output_format == "html":
        return "html5"
    if output_format == "ats":
        return "plain"
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
