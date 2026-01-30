--------------------------------------------------------------------------------
cv-workbench
cv-workbench/docs/plans/2026-01-30-preview-ux-design.md

Design for robust preview UX: auto-open, toggles, and stop flow.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------

# Preview UX hardening

## Intent

Make the preview UX "just work" without touching user browser sessions beyond
opening a new tab. The system must fail fast with explicit guidance if
automation is blocked. No silent fallbacks.

## Scope

In scope:
- Auto-open that is robust on macOS without quitting browsers.
- Visible toggles for theme/preset with keyboard shortcuts.
- Explicit stop flow for preview server.
- Clear session hygiene (minimal state file).

Out of scope:
- Long-lived preview daemon.
- Browser-specific automation beyond default browser.
- Any auto-close of browser tabs or windows.

## Option selection

Chosen approach: **Managed preview session**.

Reasoning:
- Provides best UX while keeping CLI surface stable.
- Keeps browser control limited to opening a URL.
- Adds explicit stop without interfering with user sessions.

## Design

### Auto-open (macOS)

1. Resolve default browser bundle id via LaunchServices.
2. Resolve app name from Info.plist.
3. Preflight Automation: run a no-op AppleScript to ensure permission.
4. Start server; open URL via `osascript` `open location`.
5. If any step fails, exit with explicit remediation:
   - System Settings → Privacy & Security → Automation
   - Or `CVW_SKIP_OPEN=1` for headless runs.

### Preview UI controls

Add a compact control bar (visible at all times):
- Theme dropdown
- Preset dropdown
- Rebuild button
- Stop preview button

Keep keyboard shortcuts:
- `t`: next theme
- `p`: next preset
- `r`: rebuild
- `x`: stop preview

Controls call `/api/render` and `/api/stop`. Errors show in a banner without
silently changing state.

### Stop flow

Expose `/api/stop`:
- Stops watcher
- Shuts down the HTTP server
- Returns JSON status

The UI switches to a stopped state with a restart hint.

### Session hygiene

Write a minimal session record under `runs/preview/`:
- PID, port, URL
- Theme/preset
- Start time

This is informational only; no auto-recovery or auto-restart.

## Error handling principles

- Fail fast on Automation or browser resolution errors.
- Do not attempt to open the browser if preflight fails.
- Never close user browser tabs or windows.

## Tests

- Unit tests for macOS browser resolution.
- Unit test for Automation error formatting.
- CLI tests covering:
  - open failure with actionable hint
  - `CVW_SKIP_OPEN=1` bypass

## Rollout

1. Implement preflight + AppleScript open (macOS).
2. Add UI controls + stop endpoint.
3. Document in quickstart + styling guide.
4. Ensure `cvw dev serve` prints next steps and control hints.
