# CVW Dev Spec: Zero-Friction Browser Open + Project-Centric Job Tailoring UX

## Summary

This design makes browser auto-open robust and decoupled, adds a project-centric
job tailoring workflow without mutating SoT by default, and upgrades the preview
to a single left-sidebar control center. It keeps the CLI surface tight and
MCP-ready while preserving strict validation, determinism, and auditability.

## Goals

- Auto-open works from any terminal without macOS Automation prompts by default.
- Job tailoring is a first-class project flow with evidence-backed proposals.
- Preview UI is the control center: variants, formats, styles, run history, and
  fast iteration with HTML + PDF rebuilds.

## Non-goals

- Hosted UI or SaaS dashboard.
- LLM-generated claims without evidence.
- Replacing strict schema validation or deterministic build pipeline.

## Part A — Auto-open redesign

### Design

- Introduce `cvworkbench/dev/open.py` with an `OpenMode` enum:
  - `launchservices` (default on macOS)
  - `applescript` (opt-in)
  - `none` (headless)
- `launchservices` uses `open "<url>"` and avoids Automation permissions.
- If opening fails, **server keeps running** and CLI prints a single actionable
  warning + manual URL (no silent fallback).
- `applescript` mode remains opt-in. On `-1743` errors:
  - Print Automation pane deep link
  - Suggest `--open-mode=launchservices`
  - Keep server running

### CLI surface

- Flags: `--open-mode` / env `CVW_OPEN_MODE`
- Flags: `--browser` / env `CVW_BROWSER`
- `--no-open` maps to `none`

### Acceptance

- macOS default open uses LaunchServices and does not require Automation.
- Open failures never kill the server, but always emit explicit instructions.

## Part B — Project-centric job tailoring

### Storage (default)

Projects live at repo root under `projects/` (gitignored by default), with a
config override in `config/workbench.yaml`.

```
projects/<slug>/
  project.yaml
  job/
    source.url
    extracted.txt
    signals.json
  proposals/
    patch.yaml
    variant.yaml
    notes.md
  builds/
```

### Raw HTML policy

Default is **no raw HTML**. Users opt in with `--store-raw` to write
`job/raw.html`.

### Evidence-backed proposals

Every proposal references evidence spans from `job/extracted.txt` with a
`job_evidence` list. Suggestions without evidence are marked `speculative` and
excluded by default.

### Apply semantics

- `cvw build --project <slug>` and `cvw dev serve --project <slug>` apply
  proposals **in-memory**.
- Only `cvw project apply <slug>` writes to SoT packs.

## Part C — Preview UX (single sidebar)

### UI

- One left sidebar replaces the bottom-right control bar.
- Sidebar includes:
  - Project selector
  - Variant selector
  - Theme + preset selectors
  - Format tabs: HTML | PDF | MD | ATS
  - Auto-PDF toggle (default ON)
  - Rebuild + Stop
  - Run history list

### Behavior

- Theme/variant/preset changes rebuild HTML **and** PDF automatically.
- Keyboard shortcuts map to sidebar controls (global listeners):
  - `t` theme, `p` preset, `v` variant, `f` format, `r` rebuild, `x` stop.

## Part D — CLI ergonomics

Keep MCP-ready verbs and add minimal orchestration:

- `cvw preview` (alias for `cvw dev serve` with best defaults)
- `cvw project new --job-url ... --variant ... [--open]`
- `cvw project apply <slug>`

No new implicit mutations; orchestration commands only call existing verbs.

## Testing & docs

### Tests

- `tests/dev/test_open_modes.py` for open selection + messaging.
- `tests/cli/test_dev_serve_open.py` for CLI parsing + non-fatal open failure.
- `tests/ux/test_preview_sidebar.py` for sidebar controls + rebuild behavior.
- `tests/projects/test_project_flow.py` for project scaffolding + in-memory apply.

### Docs

- `README.md`: minimal preview + project flow with links.
- `docs/howto/quickstart.md`: `cvw preview` and open modes.
- `docs/howto/ingestion.md`: `--store-raw` and evidence rules.
- `docs/reference/project-contract.md`: project layout + apply semantics.
- `docs/howto/styling.md`: sidebar UX and auto-PDF behavior.

## Open questions

- None blocking implementation.
