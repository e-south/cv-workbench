"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_render_recovery.py

Verify real Pandoc failures preserve completed outputs and remove staged artifacts.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from pathlib import Path

import pytest

from cvworkbench.build.rendering import (
    RenderError,
    RenderRequest,
    render_document,
    render_documents,
)
from cvworkbench.variants import load_variant

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def render_inputs(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("# Example\n\nCompleted content.\n")
    failure = tmp_path / "failure.lua"
    failure.write_text(
        "function Pandoc(doc)\n"
        '  local file = assert(io.open(PANDOC_STATE.output_file, "w"))\n'
        '  file:write("incomplete export")\n'
        "  file:close()\n"
        '  error("intentional render failure")\n'
        "end\n"
    )
    return source, failure, load_variant(ROOT / "config/variants/base.yaml")


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("entry", ["direct", "single", "sequential", "parallel"])
def test_failed_render_preserves_destination(tmp_path, render_inputs, existing, entry):
    source, failure, variant = render_inputs
    formats = ["md", "docx"] if entry in {"sequential", "parallel"} else ["md"]
    requests = [
        RenderRequest(source, tmp_path / f"cv.{fmt}", variant, tmp_path, fmt, None)
        for fmt in formats
    ]
    if existing:
        for request in requests:
            request.output_path.write_bytes(b"Last successful document\n")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    completed = []

    with pytest.raises(RenderError, match="intentional render failure"):
        if entry == "direct":
            render_document(
                source,
                requests[0].output_path,
                variant,
                tmp_path,
                "md",
                None,
                filter_paths=[failure],
            )
        else:
            render_documents(
                requests,
                filter_paths=[failure],
                max_workers=1 if entry == "sequential" else 2,
                after_each_success=lambda request: completed.append(request.output_path),
            )

    assert completed == []
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


@pytest.mark.parametrize("workers", [1, 2])
def test_success_callback_observes_only_completed_outputs(tmp_path, render_inputs, workers):
    source, _, variant = render_inputs
    requests = [
        RenderRequest(source, tmp_path / f"cv.{fmt}", variant, tmp_path, fmt, None)
        for fmt in ("md", "docx")
    ]
    observations = []

    def completed(request):
        observations.append((request.output_format, request.output_path.read_bytes()))

    render_documents(requests, filter_paths=[], max_workers=workers, after_each_success=completed)

    assert [fmt for fmt, _ in observations] == ["md", "docx"]
    assert b"Completed content." in observations[0][1]
    assert observations[1][1].startswith(b"PK")
    assert {path.name for path in tmp_path.iterdir()} == {
        "source.md",
        "failure.lua",
        "cv.md",
        "cv.docx",
    }


@pytest.mark.parametrize("alias", [False, True])
def test_conflicting_output_paths_fail_before_writes(tmp_path, render_inputs, alias):
    source, _, variant = render_inputs
    output = tmp_path / "cv.md"
    output.write_text("Previous document\n")
    second = tmp_path / "nested/../cv.md" if alias else output
    requests = [
        RenderRequest(source, path, variant, tmp_path, "md", None) for path in (output, second)
    ]
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}

    with pytest.raises(RenderError, match="distinct output paths"):
        render_documents(requests)

    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


@pytest.mark.parametrize("workers", [1, 2])
@pytest.mark.parametrize("error", [ValueError, KeyboardInterrupt])
def test_callback_failure_preserves_completed_prefix_and_cleans_staging(
    tmp_path, render_inputs, workers, error
):
    source, _, variant = render_inputs
    requests = [
        RenderRequest(source, tmp_path / f"cv.{fmt}", variant, tmp_path, fmt, None)
        for fmt in ("md", "docx")
    ]
    requests[1].output_path.write_bytes(b"Previous DOCX\n")
    observed = []

    def completed(request):
        observed.append(request.output_format)
        raise error("stop after first output")

    with pytest.raises(error, match="stop after first output"):
        render_documents(
            requests, filter_paths=[], max_workers=workers, after_each_success=completed
        )

    assert observed == ["md"]
    assert "Completed content." in requests[0].output_path.read_text()
    assert requests[1].output_path.read_bytes() == b"Previous DOCX\n"
    assert {path.name for path in tmp_path.iterdir()} == {
        "source.md",
        "failure.lua",
        "cv.md",
        "cv.docx",
    }
