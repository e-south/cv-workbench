"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/dev/test_preview_contract.py

Tests preview UI contract selectors for browser automation.

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
        'data-cvw-status="summary"',
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


def test_preview_page_html_preserves_unset_project_value() -> None:
    html = _preview_page_html()
    assert "const projectOptions = data.project ? [data.project] : [];" in html
    assert "syncSelect(projectSelect, projectOptions, data.project, true);" in html
    assert "allowUnset ? '' : options[0]" in html


def test_preview_page_html_declares_inline_favicon() -> None:
    html = _preview_page_html()
    assert '<link rel="icon" href="data:," />' in html


def test_preview_page_html_exposes_busy_status_messages() -> None:
    html = _preview_page_html()
    assert "Rebuilding preview..." in html
    assert "Stopping preview..." in html
    assert "pendingAction" in html
    assert "syncOverlay(state.data || {}, true);" in html


def test_preview_page_html_normalizes_shortcuts_and_ignores_modified_keys() -> None:
    html = _preview_page_html()
    assert "event.key.toLowerCase()" in html
    assert "event.metaKey || event.ctrlKey || event.altKey" in html


def test_preview_page_html_renders_summary_with_safe_text_nodes() -> None:
    html = _preview_page_html()
    assert "appendSummaryField" in html
    assert "strong.textContent = value;" in html
    assert "line.innerHTML" not in html
