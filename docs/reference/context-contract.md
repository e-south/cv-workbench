# Context Contract

`cvw context --json` is the bootstrap command for humans and agents. It reports
the current workspace state without guessing paths or falling back to defaults.
Missing inputs are surfaced explicitly in the payload.

## Guarantees

- Local-only inspection (no network access).
- Deterministic output for the current workspace.
- Explicit `sot.status` and `sot.errors` when SoT is missing or invalid.
- `recipes` provides canonical command sequences for common intents.

## Payload (JSON)

Top-level keys:
- `command`: always `context`.
- `config`: config path and project metadata.
- `sot`: configured/resolved paths, status, errors, files, sections, tags.
- `variants`: configured variants, inbox, default, TTL.
- `runs`: latest/recents per variant plus invalid directories.
- `projects`: local projects list and invalid entries.
- `reviews`: review packs inventory.
- `recipes`: ordered command sequences for common workflows.
- `issues`: any non-fatal problems detected during inspection.

## Recipe fields

Each recipe includes:

- `id` and `title`
- `preconditions`
- `steps` (each with `command` + `description`)
- `outputs`
- `stop_conditions`

Recipe ordering prioritizes:
1) Baseline build/preview
2) Review/import
3) Job tailoring project

## Strict mode

`cvw context --strict` fails fast if required inputs are missing or invalid.
Use this when automation depends on a valid SoT.
