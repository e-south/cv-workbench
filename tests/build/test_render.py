"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_render.py

Tests render command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from typer.testing import CliRunner

import cvworkbench.build.rendering as rendering_module
from cvworkbench.build.rendering import (
    RenderError,
    RenderRequest,
    render_document,
    render_documents,
)
from cvworkbench.cli import app
from cvworkbench.variants import DEFAULT_ORDER, Variant
from tests.utils import strip_ansi


def test_render_writes_output(tmp_path: Path) -> None:
    canonical_path = tmp_path / "canonical.md"
    canonical_path.write_text("# Sample\n")

    output_path = Path("var/dist/base/cv.md")
    if output_path.exists():
        output_path.unlink()

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "render",
            "--canonical",
            str(canonical_path),
            "--variant",
            "base",
            "--format",
            "md",
            "--plain",
        ],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    output = strip_ansi(result.stdout)
    assert "output_md:" in output
    assert "cv.md" in output


def test_render_documents_parallelizes_distinct_outputs(tmp_path: Path, monkeypatch) -> None:
    canonical_path = tmp_path / "canonical.md"
    canonical_path.write_text("# Sample\n")
    variant = _sample_variant(["md", "docx"])
    requests = [
        RenderRequest(
            input_path=canonical_path,
            output_path=tmp_path / "cv.md",
            variant=variant,
            filters_dir=tmp_path,
            output_format="md",
            pdf_engine=None,
        ),
        RenderRequest(
            input_path=canonical_path,
            output_path=tmp_path / "cv.docx",
            variant=variant,
            filters_dir=tmp_path,
            output_format="docx",
            pdf_engine=None,
        ),
    ]
    active = 0
    max_active = 0
    lock = threading.Lock()

    render = rendering_module._render_document
    started = threading.Barrier(2, timeout=5)

    def observe_render(*args, **kwargs) -> None:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            started.wait()
            render(*args, **kwargs)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(rendering_module, "_render_document", observe_render)

    render_documents(requests, max_workers=2)

    assert max_active > 1
    assert "Sample" in (tmp_path / "cv.md").read_text()
    assert (tmp_path / "cv.docx").read_bytes().startswith(b"PK")
    assert not list(tmp_path.glob(".cv.*"))


def test_render_documents_cleans_up_temp_outputs_on_failure(tmp_path: Path) -> None:
    canonical_path = tmp_path / "canonical.md"
    canonical_path.write_text("# Sample\n")
    variant = _sample_variant(["md", "docx"])
    requests = [
        RenderRequest(
            input_path=canonical_path,
            output_path=tmp_path / "cv.md",
            variant=variant,
            filters_dir=tmp_path,
            output_format="md",
            pdf_engine=None,
        ),
        RenderRequest(
            input_path=canonical_path,
            output_path=tmp_path / "cv.docx",
            variant=variant,
            filters_dir=tmp_path,
            output_format="docx",
            pdf_engine=None,
        ),
    ]

    filter_path = tmp_path / "failure.lua"
    filter_path.write_text(
        "function Pandoc(doc)\n"
        '  if FORMAT == "markdown" then error("md failed") end\n'
        "  return doc\n"
        "end\n"
    )

    with pytest.raises(RenderError, match="md failed"):
        render_documents(requests, filter_paths=[filter_path], max_workers=2)

    assert not (tmp_path / "cv.md").exists()
    assert not (tmp_path / "cv.docx").exists()
    assert not list(tmp_path.glob(".cv.*"))


def test_atomic_render_preserves_pdf_output_extension(tmp_path: Path) -> None:
    source = tmp_path / "canonical.md"
    source.write_text("# Sample\n")
    output = tmp_path / "cv.pdf"
    render_document(source, output, _sample_variant(["pdf"]), tmp_path, "pdf", "xelatex")

    assert output.read_bytes().startswith(b"%PDF-")
    assert {path.name for path in tmp_path.iterdir()} == {"canonical.md", "cv.pdf"}


def _sample_variant(outputs: list[str]) -> Variant:
    return Variant(
        id="base",
        include_tags=[],
        exclude_tags=[],
        max_bullets_per_role=None,
        order=list(DEFAULT_ORDER),
        outputs=outputs,
        output_name="cv",
        document_type="resume",
        letter_id=None,
        render_theme=None,
        render_style_preset=None,
    )
