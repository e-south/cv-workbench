"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_preview.py

Tests preview command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


def test_preview_once_builds_html_without_session(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md, pdf, html]",
            ]
        )
        + "\n"
    )
    root = Path(__file__).resolve().parents[2]
    themes_dir = root / "build" / "themes"
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: ../var/dist",
                "  runs: ../var/runs",
                "variants:",
                "  default: base",
                "render:",
                f"  themes_dir: {themes_dir}",
                "  theme: default",
                "  style_preset: modern",
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "preview",
            "--once",
            "--variant",
            "base",
            "--sot-path",
            "sot.sample",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 0
    html_path = tmp_path / "var" / "dist" / "base" / "cv.html"
    assert html_path.exists()
    session_path = tmp_path / "var" / "runs" / "preview" / "session.json"
    assert not session_path.exists()
