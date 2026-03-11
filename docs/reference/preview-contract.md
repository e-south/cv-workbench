# Preview Contract

The preview server is a local-only HTTP surface that exposes a minimal UI and
API for browser automation or manual inspection. The CLI is responsible for
starting and stopping the server; Chrome DevTools MCP is the preferred
interactive controller.

Only loopback hosts are supported. `CVW_DEV_HOST` may be set to `localhost`,
`127.0.0.1`, or `::1`; non-local bind addresses such as `0.0.0.0` are rejected.

## Session record

`uv run cvw preview` writes a session record to:

```
var/runs/preview/session.json
```

Fields:
- `pid`, `host`, `port`, `url`
- `variant`, `theme`, `style_preset`
- `started_at` (UTC ISO-8601)

## One-shot preview

`uv run cvw preview --once` builds the preview outputs once and exits without starting
the server. No session file is written in this mode.

## HTTP API

`GET /api/state` returns the current preview state:
- `variant`, `theme`, `style_preset`
- `themes`, `presets`, `variants`, `projects`, `project`
- `format`, `auto_pdf`, `build_id`, `last_error`
- `outputs` (format -> filename)

`POST /api/render` rebuilds with optional overrides:

```json
{
  "theme": "default",
  "style_preset": "compact",
  "variant": "base",
  "format": "html",
  "auto_pdf": true
}
```

Returns the same payload as `/api/state` on success; on failure returns
`{"error": "<message>"}` with a `400` status.

`POST /api/stop` stops the preview server and returns `{"status": "stopping"}`.

## UI control selectors (stable)

Browser automation should target the stable `data-cvw-*` hooks:

- `data-cvw-control="project|variant|theme|preset|format-tabs|auto-pdf"`
- `data-cvw-format="html|pdf|md|ats"` on each format button
- `data-cvw-active="true|false"` + `aria-pressed` on the active format button
- `data-cvw-action="rebuild|stop"`
- `data-cvw-status="status|error|run-list"`
- `data-cvw-build-id` on `<body>` (updated on successful rebuild)
- `data-cvw-view="preview-frame"`

The project selector is read-only and displays the active project (if the
preview was started with `--project`); otherwise it shows `none` instead of a
disabled list of unrelated projects.

## Interaction semantics

- `build_id` increments after each successful rebuild and is used to cache-bust
  the iframe URL.
- UI controls call `/api/render`; state updates are visible via `/api/state`.
- The UI polls `/api/state` every second while visible, and backs off when the
  tab is hidden so idle background tabs generate less request noise.
- The Stop button (or `POST /api/stop`) shuts down the server and disables UI
  controls.
- Keyboard shortcuts are ignored while focus is inside interactive controls so
  agents/operators do not accidentally rebuild or switch variants while
  navigating the sidebar.
- Browser inactivity auto-stops the preview server after 30 seconds by default.
  Set `CVW_DEV_IDLE_TIMEOUT_SECONDS=0` to disable the idle timeout.
- If the preview API becomes unreachable, the error status shows a
  "Preview disconnected" message.

## Browser automation recipe

1. Navigate to the preview URL (local-only).
2. Use Chrome DevTools MCP to capture a text snapshot, screenshot, and console
   warnings after actions or build-id changes.
3. Click the PDF tab if you need the PDF view (`[data-cvw-format="pdf"]`).
4. Focus the preview frame (`[data-cvw-view="preview-frame"]`).
5. Scroll with PageDown or mouse wheel.
6. Detect build completion by watching `body[data-cvw-build-id]` or
   `[data-cvw-status="run-list"]`.
7. Save artifacts as `ui.snapshot.md`, `ui.png`, and `console.txt`.
8. Do not spam snapshots; capture only after actions or rebuilds.
