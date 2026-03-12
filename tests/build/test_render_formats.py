"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_render_formats.py

Tests additional render formats.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import importlib
from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


def test_render_writes_html_and_docx(tmp_path: Path) -> None:
    canonical_path = tmp_path / "canonical.md"
    canonical_path.write_text("# Sample\n")

    html_path = Path("var/dist/base/cv.html")
    docx_path = Path("var/dist/base/cv.docx")
    for path in [html_path, docx_path]:
        if path.exists():
            path.unlink()

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
            "html,docx",
        ],
    )

    assert result.exit_code == 0
    assert html_path.exists()
    assert docx_path.exists()
    assert html_path.stat().st_size > 0
    assert docx_path.stat().st_size > 0


def test_render_normalizes_duplicate_variant_outputs(tmp_path: Path, monkeypatch) -> None:
    canonical_path = tmp_path / "canonical.md"
    canonical_path.write_text("# Sample\n")

    config_dir = tmp_path / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md, md, html]",
            ]
        )
        + "\n"
    )
    themes_dir = Path(__file__).resolve().parents[2] / "build" / "themes"
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: ../var/dist",
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

    captured_formats: list[str] = []
    app_module = importlib.import_module("cvworkbench.cli.app")

    def fake_render_documents(requests, **kwargs) -> None:
        after_each_success = kwargs.get("after_each_success")
        for request in requests:
            captured_formats.append(request.output_format)
            request.output_path.parent.mkdir(parents=True, exist_ok=True)
            request.output_path.write_text(request.output_format)
            if after_each_success is not None:
                after_each_success(request)

    monkeypatch.setattr(app_module, "render_documents", fake_render_documents)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "render",
            "--canonical",
            str(canonical_path),
            "--config",
            str(config_path),
            "--variant",
            "base",
            "--plain",
        ],
    )

    assert result.exit_code == 0
    assert captured_formats == ["md", "html"]
