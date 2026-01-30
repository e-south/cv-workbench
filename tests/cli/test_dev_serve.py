"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_dev_serve.py

Tests dev serve command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import os
from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


def test_dev_serve_builds_html(tmp_path: Path) -> None:
    html_path = Path("dist/base/cv.html")
    if html_path.exists():
        html_path.unlink()

    runner = CliRunner()
    env = os.environ.copy()
    env["CVW_SKIP_OPEN"] = "1"

    result = runner.invoke(
        app,
        [
            "dev",
            "serve",
            "--variant",
            "base",
            "--sot-path",
            "sot.sample",
        ],
        env=env,
    )

    assert result.exit_code == 0
    assert html_path.exists()
    assert html_path.stat().st_size > 0
