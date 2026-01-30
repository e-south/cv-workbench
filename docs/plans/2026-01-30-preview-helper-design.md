---
title: Preview Helper App Design (PDF-first)
date: 2026-01-30
status: approved
---

# Preview helper app design (PDF-first)

## Summary

Provide a guaranteed, low-friction preview window by shipping a tiny macOS helper app (`cvw-viewer`) that opens a PDF-first window and can toggle to HTML. The CLI controls the helper over localhost, ensuring a visible preview even when browsers/LaunchServices/Quick Look are unreliable. This keeps the agent loop tight: edits in chat -> CLI rebuild -> helper reload.

## Goals

- Guarantee a visible preview window on macOS without manual flags.
- Default to PDF for review, with a fast HTML toggle when needed.
- Keep the CLI as the control plane and the helper as a dumb renderer.
- Preserve determinism and auditability (no hidden state changes).
- Keep the UI minimal and focused on reviewing outputs.

## Non-goals

- No full WYSIWYG editor.
- No background sync to external services.
- No replacement of the CLI as the build system.

## Architecture

### Components

- **cvw CLI**: builds outputs, runs preview server, sends open/reload commands.
- **cvw-viewer helper app**: a small macOS app with a PDF pane (default) and HTML pane.
- **Preview server**: existing `cvw dev serve` HTML preview with controls.

### Control channel

The CLI sends commands to the helper via a local HTTP endpoint. The helper must:

- accept an `open` command to show a window and load the PDF + HTML URL
- accept a `reload` command to refresh PDF and HTML when builds change
- expose a `health` endpoint for liveness/version checks

Example contract:

```
POST /open
{
  "pdf_path": "/path/to/dist/base/cv.pdf",
  "html_url": "http://127.0.0.1:8765/",
  "focus": true
}

POST /reload
{
  "pdf_path": "/path/to/dist/base/cv.pdf",
  "html_url": "http://127.0.0.1:8765/"
}

GET /health
-> { "running": true, "version": "1.0.0" }
```

### Default behavior

- `cvw preview` starts the preview server and sends `open` to the helper.
- The helper window opens with the PDF selected and the HTML tab ready.
- On rebuild, CLI sends `reload` and the helper refreshes in place.

### Error handling (no silent fallback)

- If helper is unavailable, the CLI prints a clear error and falls back to
  browser preview (existing behavior) with explicit messaging.
- If the helper fails to reload, the CLI prints an error and leaves the server running.
- The helper never mutates SoT or build artifacts.

## UX details

- **PDF-first**: user sees a PDF immediately, no browser tab required.
- **HTML toggle**: one click to switch to the HTML preview controls.
- **Single window**: no new windows on each refresh.
- **Agent loop**: CLI prints a concise update when a refresh completes.

## Distribution

- Prebuilt helper app is downloaded on first use (cached under `~/.cvw/viewer/`).
- CLI verifies checksums and version before launching.
- Updates are opt-in via CLI (no silent updates).

## Security posture

- Helper only binds to loopback (127.0.0.1).
- No network calls beyond local control channel.
- Explicit opt-in for installing the helper binary.

## Performance notes

- Helper only renders a PDF and an HTML tab; no heavy background work.
- CLI keeps the render pipeline unchanged; only the preview open/reload is new.
- Use lightweight caching for any repeated discovery or health checks.

## Testing

- Unit tests: CLI command selection and health-check logic.
- Integration tests: `preview -> open -> reload` with a mocked helper.
- Manual QA: start/stop helper, verify window stays in front, verify reloads.

## Rollout plan

1. Add helper control code to `cvw preview` with a feature flag (disabled by default).
2. Ship helper app and enable PDF-first helper by default on macOS.
3. Document fallback paths and troubleshooting steps.
4. Iterate on window focus and reload fidelity.

## Open questions

- Signing/notarization requirements for the helper app distribution.
- Whether we should support non-macOS helpers (Windows/Linux) later.
