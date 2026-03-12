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
- `session_id` (opaque lease id for the current preview server instance)
- `project` (when preview was started with `--project`)
- `started_at` (UTC ISO-8601)

## One-shot preview

`uv run cvw preview --once` builds the HTML preview output once and exits
without starting the server. No session file is written in this mode. Pass
`--with-pdf` when you also need a one-shot `cv.pdf`. With `--project`, the
rendered files stay under `var/runs/preview/<project-id>/`. When `--sot-path`
points at a concrete version directory, preview uses that exact directory
instead of following `ACTIVE`.

## HTTP API

`GET /api/state` returns the current preview state:
- `session_id`
- `variant`, `theme`, `style_preset`
- `themes`, `presets`, `variants`, `projects`, `project`
- `format`, `auto_pdf`, `build_id`, `last_error`
- `project_context` (when preview was started with `--project`):
  `proposal_document_type`, `patch_status`, `patch_operations`,
  `render_warning`, plus any `proposal-plan.json` guidance fields that were
  available (`recommended_variant`, `recommendation_status`,
  `recommendation_summary`, `job_keywords_missing`, `steps`). If preview can
  still render the project patch but detailed project metadata is incomplete,
  `project_context_error` is returned instead of silently omitting the failure.
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
- `data-cvw-status="status|error|summary|project-guidance|project-warning|run-list|controller-pill|build-pill"`
- `data-cvw-build-id` on `<body>` (updated on successful rebuild)
- `data-cvw-session-id` on `<body>` (current preview lease id)
- `data-cvw-controller-state="active|passive|stopped|disconnected"` on `<body>`
- `data-cvw-view="preview-frame"`

The project selector is read-only and displays the active project (if the
preview was started with `--project`); otherwise it shows `none` instead of a
disabled list of unrelated projects. For project-scoped preview, the sidebar
also mirrors the current proposal lane via `project-guidance` and
`project-warning`, including any cover-letter visibility warning when
`project-ops` target resume-only content. If project guidance metadata cannot
be loaded, the sidebar warns explicitly instead of silently collapsing to a
project-id-only payload. The preview UI is a render-control surface, not a
content editor.

## Interaction semantics

- `build_id` increments after each successful rebuild and is used to cache-bust
  the iframe URL.
- UI controls call `/api/render`; state updates are visible via `/api/state`.
- Non-force theme, preset, variant, format, and auto-PDF changes are briefly
  debounced and coalesced in the browser so rapid control changes collapse into
  one rebuild instead of multiple back-to-back renders.
- Format switches reuse already-built outputs immediately when the requested
  artifact is already present; the Rebuild button remains the explicit
  force-refresh control.
- The UI polls `/api/state` every second while visible, and backs off when the
  tab is hidden so idle background tabs generate less request noise.
- Summary/build metadata is only re-painted when the visible state actually
  changes, which avoids unnecessary DOM churn during steady-state polling.
- Only one browser tab is treated as the active controller for a given
  `session_id`. When a newer tab claims the same preview session, older tabs
  become passive, disable controls, and stop polling until they regain focus.
  If the active tab releases the session, passive peers stay passive until a
  focused tab explicitly reclaims control; release does not silently reactivate
  every open tab at once.
- The Stop button (or `POST /api/stop`) shuts down the server and disables UI
  controls. A successful stop also broadcasts the stopped state to other open
  tabs for the same `session_id`; the tabs remain open but visibly disabled.
- Keyboard shortcuts are ignored while focus is inside interactive controls so
  agents/operators do not accidentally rebuild or switch variants while
  navigating the sidebar.
- Browser inactivity auto-stops the preview server after 30 seconds by default.
  Set `CVW_DEV_IDLE_TIMEOUT_SECONDS=0` to disable the idle timeout.
- If the preview API becomes unreachable, the error status shows a
  "Preview disconnected" message.
- Starting a new preview session against a workspace with an already-live
  session fails fast with a reuse/stop hint; stale session records are cleared
  automatically before startup continues.

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
