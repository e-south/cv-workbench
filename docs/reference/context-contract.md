---
id: reference-context-contract
intent: Define the deterministic bootstrap payload for humans and agents.
audience: [agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

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
- `recommended_workflows` only points to workflows that are actionable in the
  current workspace state. For example, `review.import` is only recommended
  when a review-ready run already includes `cv.docx`, `cv.pdf`, and
  `selection.json`.
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
- `recipes` includes an explicit `project.inspect` lane so agents can inspect a
  proposal before previewing, reviewing, or applying it.

## Python inspection API

```python
from pathlib import Path
from cvworkbench.workspace.context import inspect_workspace

state = inspect_workspace(
    config=Path("config/workbench.yaml"),
    sot_path=None,
    strict=False,
    compact=False,
)
```

The API returns the context state without a CLI `command` envelope. It performs
local reads and returns data without printing or writing workspace files. With
`strict=False`, recoverable inventory problems appear in `issues` and the
corresponding section. With `strict=True`, the first such problem raises
`ValueError`. An unreadable or invalid workbench configuration fails in either
mode. CLI adapters translate these errors into their terminal message and exit
code; Python callers handle the exception themselves.

`compact=True` limits inventory work (for example, one recent run per variant)
and omits detailed run/project/review items. The API still returns full recipe
descriptions. CLI compact presentation additionally reduces source/variant
details and recipes to the documented summary representation. See the
[architecture owner map](../concepts/architecture.md#workspace-inspection-and-command-adapters)
before extending inspection or recipe behavior.

## Payload (JSON)

Top-level keys:
- `command`: always `context`.
- `config`: config path and project metadata.
- `sot`: configured/resolved paths, status, errors, files, sections, tags.
- `variants`: configured variants, inbox, default, TTL.
  Project inbox entries include selector metadata plus ready-to-run
  `keep_command`, `discard_command`, and `preview_command` strings.
- `runs`: latest/recents for configured top-level variants plus invalid directories.
  Project-scoped runs are inspected via `project show` or explicit
  `reviewpack --project/--run` resolution so variant inventory is not polluted
  by newer project-only runs.
- `projects`: local projects list and invalid entries.
- `reviews`: actual review packets, including nested project/run packs and
  publication packets. Each full entry includes `kind` (`content` or
  `publication`) and its review path. Container directories are not review
  items. Inventory presence is not proof of publication approval or freshness.
  Partial packets remain visible with an explicit `missing_files` list.
  Content entries include a `source` object reporting the recorded run and its
  baseline state (`ready`, `changed`, `missing`, `invalid`, or `untracked`).
  Plain/compact summaries include that state. See
  [Content Review](review-contract.md#provenance-and-health) for its meaning;
  `ready` does not mean human approval.
- `publication`: the declared site's authored publication, including current
  source/export paths, PDF hash, packet path, phase and explicit reasons.
  It remains present in compact output. Inspection hashes current files and
  verifies packet integrity; the default generated-document variant does not
  select this publication. Missing configuration is reported without guessing.
- `recipes`: ordered command sequences for common workflows.
  `authored.publish` routes source preparation, a non-runnable manual review
  step, exact-hash review recording, and guarded local sync. Configured
  publications receive a recommendation when the structured workspace is ready.
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
6) Project inspection / proposal lifecycle

## Strict mode

`uv run cvw context --strict` fails fast if required inputs are missing or invalid.
Use this when automation depends on a valid SoT.
