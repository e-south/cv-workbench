# Live Preview + SoT Version Packs Design

## Context
We want a fast, low-friction iteration loop for CV output styling and content
while keeping the system decoupled, auditable, and reproducible. The current
CLI already renders via Pandoc with theme packs. This design adds a live preview
loop and a versioned SoT model that makes experimentation safe without relying
on a single mutable source.

## Goals
- Auto-build and auto-reload preview with minimal user friction.
- Keep theme/preset toggles fast, visual, and safe (no silent changes).
- Allow SoT experimentation without destroying the canonical version.
- Keep CLI surface tight and MCP-friendly.

## Non-goals
- Building a full WYSIWYG editor or storing edits in DOCX.
- Implicitly modifying SoT or config from the preview UI.
- Expanding variant creation or saving from the preview loop.

## Design Summary
### Live preview
- `cvw dev serve` becomes the happy-path command.
- Auto-open browser; on failure, print a single manual open command.
- File watcher triggers rebuild on changes to SoT, theme templates/styles, or
  variants. Debounce rebuilds to avoid thrash.
- HTML preview auto-reloads after rebuild.
- Minimal overlay in the preview:
  - Shows current `variant`, `theme`, `style_preset`.
  - Keyboard toggles: `t` (theme), `p` (preset), `r` (rebuild).
  - No variant creation or SoT writes.
- Overlay calls `POST /api/render` with theme/preset selections; server validates
  and rebuilds, or fails fast with an error banner.

### SoT version packs
- Store SoT versions in `sot/versions/<name>/`.
- Active version selected by `sot/ACTIVE` pointer file.
- CLI namespace:
  - `cvw sot list`
  - `cvw sot new <name> --from <base>`
  - `cvw sot activate <name>`
  - `cvw sot diff <a> <b>` (structural diff)
- Dev server watches `sot/ACTIVE` and active version contents.

## Invariants and error handling
- No silent fallbacks: unknown theme/preset/version fails fast.
- Preview overlay lists only discovered themes/presets.
- Render plan remains deterministic and auditable.

## Tests
- `dev serve` rebuilds and reloads on file changes.
- `sot activate` switches version and triggers rebuild.
- Invalid theme/preset/version causes explicit error output.
- Browser open failure prints a warning and manual open command.

## Open questions
- Should `cvw dev serve` default to `--sot-path ./sot` or respect config only?
- Do we need a `cvw dev serve --no-open` flag in addition to `CVW_SKIP_OPEN=1`?
