# Preview Contract

The preview server is a local-only HTTP surface that exposes a minimal UI and
API for Playwright-driven interaction. The CLI is responsible for starting and
stopping the server; Playwright (or a human) drives the UI.

## Session record

`cvw preview` writes a session record to:

```
var/runs/preview/session.json
```

Fields:
- `pid`, `host`, `port`, `url`
- `variant`, `theme`, `style_preset`
- `started_at` (UTC ISO-8601)

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

Playwright should target the `data-cvw-*` hooks:

- `data-cvw-control="project|variant|theme|preset|format-tabs|auto-pdf"`
- `data-cvw-format="html|pdf|md|ats"` on each format button
- `data-cvw-action="rebuild|stop"`
- `data-cvw-status="status|error|run-list"`
- `data-cvw-view="preview-frame"`

The project selector is read-only unless the preview was started with
`--project`.

## Interaction semantics

- `build_id` increments after each successful rebuild and is used to cache-bust
  the iframe URL.
- UI controls call `/api/render`; state updates are visible via `/api/state`.
- The Stop button (or `POST /api/stop`) shuts down the server and disables UI
  controls.
