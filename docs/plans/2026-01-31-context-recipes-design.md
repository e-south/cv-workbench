# Context Recipes Design

## Summary

This design defines the canonical, agent-friendly recipes emitted by
`cvw context --json`. Recipes are ordered and written to minimize user friction
for a new agent in the repo. They must be deterministic, fail fast on missing
inputs, and avoid hidden fallbacks or guessed paths.

## Goals

- Provide a single bootstrap surface for agents that maps user intent to the
  correct CLI commands.
- Ensure commands are explicit, deterministic, and local-only.
- Minimize friction by using real values from context when available.
- Make stop conditions explicit (no silent fallbacks).

## Non-goals

- No automation of destructive actions without explicit approval.
- No implicit network access beyond the CLI commands explicitly invoked.

## Ordering

Recipes should be ordered for first-time agent usage:

1) Baseline build/preview (A)
2) Review/import (C)
3) Job tailoring project (B)

This ordering aligns with a “show me what we have” intent, then iteration, then
heavier-weight tailoring.

## Recipe structure

Each recipe must include:

- `id` and `title`
- `preconditions`
- `steps` (command + description)
- `outputs` (where to find artifacts)
- `stop_conditions` (explicitly instruct the agent to ask for missing inputs)

Recipes should use concrete values from the context payload (e.g. `sot.path`,
`variants.default`, `projects.items[0].project_id`). If values are missing, use
placeholders and instruct the agent to ask the user.

## Recipe content

### A) Baseline build/preview

- Preconditions: `sot.status == "ready"`, `variants.default` present.
- Steps:
  - `cvw status --sot-path <sot>`
  - `cvw build --sot-path <sot> --variant <default> --format md,pdf`
  - `cvw preview --sot-path <sot> --variant <default>`
- Outputs: `var/dist/<variant>/`, `var/runs/<id>/` (manifest, selection, canonical).
- Stop: if SoT missing/invalid, ask for the correct SoT path or config updates.

### C) Review/import (DOCX)

- Preconditions: a run exists for the target variant
  (`runs.latest_by_variant[variant]` present).
- Steps:
  - `cvw reviewpack --variant <variant>`
  - Human edits `cv.docx`
  - `cvw import-docx --from <path> --variant <variant>`
  - Optional (explicit approval): `cvw apply --draft <draft-dir> --sot-path <sot>`
- Outputs: `var/reviews/<variant>/`, `var/drafts/import-*/`.
- Stop: if no runs, run the baseline build recipe first.

### B) Job tailoring project

- Preconditions: SoT ready + job input (URL or file).
- Steps:
  - `cvw project guide --job-url <url> --sot-path <sot>` (or `--job-file`)
  - `cvw preview --project <project-id> --sot-path <sot>`
  - Optional (explicit approval): `cvw project apply <project-id>`
- Outputs: `var/projects/<slug>/` (signals, variant draft, patch).
- Stop: if job input is missing, ask for a URL or file.

## Error handling + automation cues

- `sot.status` is the primary gate. If missing/invalid, stop and ask for the
  SoT path or config update.
- Destructive actions (`project apply`, `variant discard`, `runs gc --yes`) are
  never automatic; they must be clearly marked as optional steps requiring
  explicit approval.
- The `issues` list from context should be surfaced to the user before any
  recipe execution.
