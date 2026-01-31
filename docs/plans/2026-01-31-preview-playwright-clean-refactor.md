# Preview + Clean Refactor (Playwright-First)

## Goals
- Reduce repo-root cognitive load with a strict source vs. local/artifact split.
- Make preview automation Playwright-first, interactive, and explicit.
- Remove legacy preview open modes/viewers and any fallback behavior.
- Make clean operations explicit, predictable, and confined to local artifacts.

## Scope
- Repo layout: introduce `local/` and `var/` and move local artifacts out of root.
- Preview: CLI serves and reports session info only; Playwright drives the UI.
- Clean: remove all prior runs/artifacts under `var/` with explicit dry-run/--yes.
- Docs/tests: align all references to new layout and preview contract.

## Non-Goals
- No backward compatibility shims for old paths or preview flags.
- No OS-level auto-open or browser detection.
- No changes to the render pipeline beyond the preview/open surface.

## Repo Layout Contract
```
cv-workbench/
├── local/
│   └── sot/
├── var/
│   ├── dist/
│   ├── runs/
│   ├── drafts/
│   ├── reviews/
│   ├── registry/
│   └── projects/
├── config/
├── src/
├── tests/
├── build/
├── docs/
└── sot.sample/
```
- `config/workbench.yaml` paths target `../local` and `../var`.
- Root contains only source, configuration, and documentation.

## Preview Contract (Playwright-First)
- `cvw preview` starts a local HTML preview server and prints a preview URL.
- The CLI writes a session record to `var/runs/preview/session.json`.
- Playwright is the canonical interactive controller:
  - open the preview URL
  - click/drive UI controls
  - listen for UI changes and reloads
  - capture artifacts (snapshot/screenshot/console warnings) as needed
- Preview UI exposes stable `data-cvw-*` selectors (documented in
  `docs/reference/preview-contract.md`).
- HTTP API is limited to `/api/state`, `/api/render`, and `/api/stop`.
- No auto-open, no viewer selection, no OS-level automation.
- Any legacy preview flags/vars fail fast with a clear error.

## Clean Contract
- `cvw clean` operates only under `var/`.
- Default is dry-run; `--yes` performs deletion.
- Explicit output lists what will be removed.
- `local/` is never touched.

## Tests
- Preview: session file written; preview UI has stable control selectors.
- CLI: legacy preview flags rejected with clear errors.
- Clean: dry-run output and deletion behavior in temp paths.

## Docs
- Update `AGENTS.md`, README, quickstart, styling guides to reflect:
  - Playwright-first preview workflow
  - new repo layout and paths
  - clean behavior
- Archive or remove docs that describe legacy preview behavior.
