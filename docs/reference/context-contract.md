# Context Contract

`uv run cvw context --json` is the bootstrap command for humans and agents. It reports
the current workspace state without guessing paths or falling back to defaults.
Missing inputs are surfaced explicitly in the payload.

## Guarantees

- Local-only inspection (no network access).
- Deterministic output for the current workspace.
- Explicit `sot.status` and `sot.errors` when SoT is missing or invalid.
- `recipes` provides canonical command sequences for common intents.
- When `./sot.sample` exists and the configured SoT is not ready, `recipes` adds
  an explicit sample bootstrap lane instead of silently switching inputs.
- When the configured SoT points at `./local/sot` and that scaffold is missing,
  `recipes` adds an explicit local bootstrap lane.
- When the configured SoT is missing or invalid, `recommended_workflows`
  prioritizes an explicit repair lane (`repair.sot_path` or `repair.sot_yaml`)
  before suggesting build or preview flows.
- `recipes` includes an automation-friendly smoke recipe that prefers markdown
  build output plus `preview --once` for noninteractive verification.
- `recommended_workflows` points to the next 1-3 recipe ids to inspect, with a
  reason plus exact `command` and `json_command` follow-up strings for each.
- Recipe steps preserve nondefault config/workspace context so follow-up
  commands remain valid when the workspace config lives outside the current
  directory.
- Recipe steps are machine-actionable: each step includes `kind`
  (`command|manual`), `runnable` (`true|false`), and `placeholders`.
- Project proposal recipe steps are selector-first (`--project <project-id>`)
  instead of teaching raw `proposals/variant.yaml` paths.

## Payload (JSON)

Top-level keys:
- `command`: always `context`.
- `config`: config path and project metadata.
- `sot`: configured/resolved paths, status, errors, files, sections, tags.
- `variants`: configured variants, inbox, default, TTL.
  Project inbox entries include selector metadata plus ready-to-run
  `keep_command`, `discard_command`, and `preview_command` strings.
- `runs`: latest/recents per variant plus invalid directories.
- `projects`: local projects list and invalid entries.
- `reviews`: review packs inventory.
- `recipes`: ordered command sequences for common workflows.
- `recommended_workflows`: the next workflow recipes to inspect first.
- `issues`: any non-fatal problems detected during inspection.

Use `uv run cvw workflow` to render the same `recipes` payload in a
human-readable CLI view.

Use `uv run cvw context --json --compact` for bootstrap, logs, and agent
handoff when you do not need full SoT/run/project inventories. Compact mode
keeps the same top-level object categories but collapses them to summary/count
fields and a recipe index (`id` + `title`).

For machine-readable recipe retrieval, use:

`uv run cvw workflow --id <recipe-id> --json --compact`

or replay the exact `recommended_workflows[*].json_command` string emitted by
`context --json --compact`. Treat emitted command strings as authoritative; they
may include `uv run --project <repo> cvw ...` when invoked outside the repo
root.

## Recipe fields

Each recipe includes:

- `id` and `title`
- `preconditions`
- `steps` (each with `command`, `description`, `kind`, `runnable`,
  `placeholders`)
- `outputs`
- `stop_conditions`

Recipe ordering prioritizes:
1) Repair/bootstrap lanes when `sot.status != 'ready'`
2) Baseline build/preview
3) Automation-friendly smoke verification
4) Review/import
5) Job tailoring project

## Strict mode

`uv run cvw context --strict` fails fast if required inputs are missing or invalid.
Use this when automation depends on a valid SoT.
