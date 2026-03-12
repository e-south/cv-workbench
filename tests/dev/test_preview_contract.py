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
        "data-cvw-build-id",
        "data-cvw-session-id",
        "data-cvw-controller-state",
        'data-cvw-status="controller-pill"',
        'data-cvw-status="build-pill"',
        'data-cvw-status="summary"',
        'data-cvw-status="project-guidance"',
        'data-cvw-status="project-warning"',
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


def test_preview_page_html_uses_visibility_aware_refresh_loop() -> None:
    html = _preview_page_html()
    assert "VISIBLE_REFRESH_MS = 1000" in html
    assert "HIDDEN_REFRESH_MS = 4000" in html
    assert "document.visibilityState === 'visible'" in html
    assert "document.addEventListener('visibilitychange'" in html
    assert "window.addEventListener('focus'" in html
    assert "scheduleRefresh(true);" in html


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
    assert "Queued rebuild..." in html
    assert "Finishing current rebuild; next change queued..." in html
    assert "Stopping preview..." in html
    assert "pendingAction" in html
    assert "syncOverlay(state.data || {}, true);" in html


def test_preview_page_html_exposes_single_controller_tab_contract() -> None:
    html = _preview_page_html()
    assert "PASSIVE_CONTROLLER_MESSAGE" in html
    assert "BroadcastChannel" in html
    assert "Controller active in another tab" in html
    assert "data-cvw-controller-state" in html


def test_preview_page_html_requires_focus_before_reclaiming_released_controller() -> None:
    html = _preview_page_html()
    assert "CONTROLLER_AVAILABLE_MESSAGE" in html
    assert "controllerClaimAvailable" in html
    assert "document.hasFocus()" in html
    assert "claimController('release')" in html


def test_preview_page_html_broadcasts_stop_state_to_peer_tabs() -> None:
    html = _preview_page_html()
    assert "message.type === 'stopped'" in html
    assert "type: 'stopped'" in html
    assert "handleRemoteStop" in html
    assert "window.addEventListener('pagehide'" in html


def test_preview_page_html_short_circuits_local_format_switches() -> None:
    html = _preview_page_html()
    assert "canApplyLocalFormatChange" in html
    assert "applyLocalFormatChange" in html
    assert "renderInFlight" in html
    assert "queuedRenderRequest" in html


def test_preview_page_html_debounces_expensive_render_changes() -> None:
    html = _preview_page_html()
    assert "RENDER_SETTLE_MS = 180" in html
    assert "scheduledRenderTimer" in html
    assert "scheduledRenderRequest" in html
    assert "scheduleRenderRequest" in html
    assert "performRenderRequest" in html
    assert "clearScheduledRender" in html


def test_preview_page_html_syncs_summary_incrementally() -> None:
    html = _preview_page_html()
    assert "summarySignature" in html
    assert "syncSummary" in html
    assert "buildPill" in html


def test_preview_page_html_syncs_project_guidance_incrementally() -> None:
    html = _preview_page_html()
    assert "projectGuidanceSignature" in html
    assert "syncProjectGuidance" in html
    assert "project_context" in html
    assert "project_context_error" in html


def test_preview_page_html_normalizes_shortcuts_and_ignores_modified_keys() -> None:
    html = _preview_page_html()
    assert "event.key.toLowerCase()" in html
    assert "event.metaKey || event.ctrlKey || event.altKey" in html


def test_preview_page_html_renders_summary_with_safe_text_nodes() -> None:
    html = _preview_page_html()
    assert "appendSummaryField" in html
    assert "strong.textContent = value;" in html
    assert "line.innerHTML" not in html
