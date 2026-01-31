"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/dev/test_preview_contract.py

Tests preview UI contract selectors for Playwright automation.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from cvworkbench.dev.preview import _preview_page_html


def test_preview_contract_selectors_present() -> None:
    html = _preview_page_html()
    markers = [
        'data-cvw-control="project"',
        'data-cvw-control="variant"',
        'data-cvw-control="theme"',
        'data-cvw-control="preset"',
        'data-cvw-control="format-tabs"',
        'data-cvw-control="auto-pdf"',
        'data-cvw-action="rebuild"',
        'data-cvw-action="stop"',
        'data-cvw-build-id',
        'data-cvw-view="preview-frame"',
    ]
    for marker in markers:
        assert marker in html


def test_preview_page_html_guards_control_render() -> None:
    html = _preview_page_html()
    assert "lastControlsKey" in html
    assert "nextControlsKey !== lastControlsKey" in html


def test_preview_page_html_guards_preview_src_updates() -> None:
    html = _preview_page_html()
    assert "currentPreviewSrc" in html
    assert "nextPreviewSrc !== currentPreviewSrc" in html


def test_preview_page_html_marks_active_format_button() -> None:
    html = _preview_page_html()
    assert "data-cvw-active" in html
    assert "aria-pressed" in html


def test_preview_page_html_handles_state_fetch_errors() -> None:
    html = _preview_page_html()
    assert "connectionError" in html
    assert "Preview disconnected" in html
