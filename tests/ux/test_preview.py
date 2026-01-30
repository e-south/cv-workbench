"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ux/test_preview.py

Tests preview controller behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from cvworkbench.dev.preview import PreviewController, _preview_page_html


def test_preview_controller_watch_paths() -> None:
    config_path = Path("config/workbench.yaml")
    controller = PreviewController(
        sot_base=Path("sot.sample"),
        config_path=config_path,
        variant_id="base",
        theme_id="default",
        style_preset="modern",
    )

    paths = controller.resolve_watch_paths()

    assert paths


def test_preview_page_html_contains_controls() -> None:
    html = _preview_page_html()

    assert 'id="theme-select"' in html
    assert 'id="preset-select"' in html
    assert 'id="stop-preview"' in html
