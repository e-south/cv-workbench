"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/dev/test_workspace_isolation.py

Verify repository tests preserve the operator workspace they are launched from.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cvworkbench.ops.scaffold import init_project

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("iteration", [0, 1])
def test_each_test_starts_in_an_empty_working_directory(iteration: int) -> None:
    working = Path.cwd()
    assert working != ROOT
    assert not list(working.iterdir())
    (working / "test-owned-marker").write_text(str(iteration))


def _inventory(root: Path) -> dict[str, str | None]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        if path.is_file()
        else None
        for path in root.rglob("*")
    }


def test_test_execution_preserves_operator_workspace(tmp_path: Path) -> None:
    operator = tmp_path / "operator"
    init_project(operator, sample_default=True)
    for relative in (
        "var/dist/base/cv.md",
        "var/dist/base/cv.html",
        "var/dist/base/cv.docx",
        "var/dist/base/manifest.json",
        "var/runs/2026-01-01T00-00-00Z/resume.json",
    ):
        path = operator / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"Operator-owned document\n")
    before = _inventory(operator)
    nodes = (
        "tests/build/test_build.py::test_build_generates_markdown",
        "tests/build/test_render_formats.py::test_render_writes_html_and_docx",
        "tests/cli/test_dev_serve.py::test_dev_serve_builds_html",
        "tests/ops/test_diff.py::test_diff_resume_json_output",
    )
    environment = os.environ.copy()
    environment.pop("CVW_TEMPLATE_DIR", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            *(str(ROOT / node) for node in nodes),
        ],
        cwd=operator,
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert _inventory(operator) == before
