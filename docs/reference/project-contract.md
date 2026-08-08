---
id: reference-project-contract
intent: Define private tailoring workspaces, proposal state, and guarded application.
audience: [operator, agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Project Contract

Projects are local, private workspaces for job tailoring. They keep job context,
signals, and proposal drafts without mutating the Source of Truth unless you
explicitly apply a patch.

URL ingestion is intentionally strict: only public `https` targets are valid
for `--job-url`. Internal or local content must be passed via `--job-file`.

`project guide` ranks variants, auto-applies the top eligible recommendation to
the scaffolded project when `--variant` is omitted, records deterministic
evidence-backed rationale in `job/proposal-plan.json`, and scaffolds proposal
artifacts. If you pass `--variant`, that explicit lane is preserved. The
command does not perform free-form NL rewriting of your SoT. If the
auto-retarget step fails, the command aborts and removes the partial project
workspace instead of leaving a half-created proposal behind.

## Commands

- `uv run cvw project guide --job-url <url>` or `--job-file <path>`: create a project
  and summarize SoT/job signals with variant recommendations.
- `uv run cvw project new --job-url <url>` or `--job-file <path>`: create a project
  without generating guidance output.
- `uv run cvw project show <slug>`: inspect the project proposal, patch status,
  latest project run, review readiness, ready-to-run next commands, the
  `proposal-plan.json` guidance summary (recommended variant, missing job
  keywords, next steps), and any proposal-visibility warning when
  `project-ops` target resume content that the selected proposal variant does
  not render, without mutating the SoT.
- `uv run cvw preview --project <slug> [--sot-path <path>]`: preview with project patch
  applied in-memory, optionally against an explicit SoT override. Project preview
  renders stay inside `var/runs/preview/<slug>/`. When `--sot-path` points at a
  concrete version directory, preview stays pinned to that exact directory. The
  preview sidebar mirrors project guidance and patch visibility so operators can
  see whether `project-ops` target content that the current proposal document
  type will not render. If the preview can render but project guidance metadata
  is incomplete, the sidebar reports that failure explicitly instead of hiding
  it.
- `uv run cvw reviewpack --project <slug>`: package the latest review-ready
  project-scoped run for review. Use `project show <slug>` after building to
  get the pinned `--run` command for the current immutable run.
- `uv run cvw reviewpack --run projects/<slug>/<run-id> [--force]`: package a specific
  immutable project-scoped run, optionally replacing an existing review pack directory.
- `uv run cvw import-docx --from <docx> --project <slug>`: import a reviewed DOCX against
  the latest project-scoped canonical output.
- `uv run cvw project apply <slug>`: apply the patch to your SoT on disk.

## Default location

Projects live under `var/projects/` by default (gitignored). Override the path in
`config/workbench.yaml`:

```yaml
paths:
  projects: ../var/projects
```

## Layout

```
var/projects/<slug>/
  project.yaml
  job/
    source.url        # or source.path
    extracted.txt
    signals.json
    proposal-plan.json
    raw.html          # only if --store-raw
  proposals/
    variant.yaml
    patch.yaml
```

## Variant lifecycle

Project proposal variants are ephemeral until explicitly kept. They are tracked
in `var/variants/registry.json` and expire based on
`variant_lifecycle.ttl_days` in `config/workbench.yaml`.

Use:
- `uv run cvw variant inbox` to list pending proposals.
- `uv run cvw variant keep --project <slug> --id <new-id>` to promote a proposal into
  `config/variants/`.
- `uv run cvw variant discard --project <slug> --yes` to discard proposal artifacts.
- `uv run cvw variant gc --yes` to remove expired proposal artifacts.

## Apply semantics

- `uv run cvw build --project <slug>` and `uv run cvw preview --project <slug>` apply proposal
  patches in-memory.
- Project builds write rendered artifacts into `var/runs/projects/<slug>/<run-id>/`
  instead of overwriting shared `var/dist/<variant>/`.
- `uv run cvw project show <slug>` reports the current proposal variant id,
  patch status, proposal-plan guidance, job source, latest project run, and
  replayable preview/build/apply/keep/discard commands.
- When the latest project run is review-ready, `project show` emits a pinned
  `reviewpack --project <slug> --run <run-id>` command. Otherwise it reports
  `review.status=build_required` and points back to
  `build --project <slug> --format md,pdf,docx`.
- Compare project output against an explicit baseline run before review/export
  with `uv run cvw diff --artifact canonical --run-a <base-run> --run-b
  projects/<slug>/<run-id>` or `--artifact resume`. For rendered visual review,
  use `uv run cvw compare --run-a <base-run> --run-b projects/<slug>/<run-id>`.
  Use explicit run ids or run paths from `build` / `project show` rather than
  guessing a latest baseline.
- `uv run cvw reviewpack --run projects/<slug>/<run-id>` packages a specific project build
  deterministically when multiple runs exist. Review packs now source DOCX/PDF/selection
  metadata from the selected run directory, not the shared `var/dist/<variant>/` directory.
- Variant-level `var/dist/<variant>/manifest.json` and `selection.json` are deterministic
  across identical rebuilds; run-scoped manifests keep `created_at` so run catalogs can
  still sort immutable runs.
- `uv run cvw project apply <slug>` applies the patch to your SoT on disk.

## Patch format

New project scaffolds use an explicit project-op payload:

```yaml
patch:
  format: project-ops
  operations: []
```

Empty operations mean no project-local content edits yet.

`project-ops` are now executable for guarded experience bullet replacements and
project summary replacements. To author them without hand-editing YAML, use:

```bash
uv run cvw project patch replace-experience-bullet <slug> \
  --role-id <role-id> \
  --bullet-id <bullet-id> \
  --new-text "Replacement text"

uv run cvw project patch replace-project-summary <slug> \
  --project-id <project-id> \
  --new-text "Replacement text"
```

If `--old-text` is omitted, each command snapshots the current SoT source text
into the op before writing `proposals/patch.yaml`.

The resulting operation names a stable target plus the expected source text,
then provides the replacement text:

```yaml
patch:
  format: project-ops
  operations:
    - op: replace-experience-bullet
      role_id: role-1
      bullet_id: bullet-1
      old_text: Built platform foundations.
      new_text: Built platform foundations for regulated delivery.
    - op: replace-project-summary
      project_id: project-1
      old_text: Example summary.
      new_text: Example summary tailored for regulated delivery.
```

This is a compare-and-set contract:
- `build --project` and `preview --project` compile the op list against the
  current SoT and render from a project-local copy.
- `project apply` applies the same compiled diff to the live SoT on disk.
- If the target role/bullet/project is missing, duplicated, or the current text
  no longer matches `old_text`, the command fails fast instead of silently
  rewriting the wrong content.

`import-docx` now writes `var/drafts/import-*/patch.yaml` using the same
`project-ops` schema when reviewed Experience bullets or Projects summaries map
cleanly back to SoT ids. Canonical markdown now follows the same variant
selection gates as rendered review artifacts, so filtered project imports no
longer fall back to `review_diff_only` just because hidden items were present
in the unrendered canonical source. Formatting-only normalized imports report
`apply_status: ready_no_changes`. Every import draft also writes
`var/drafts/import-*/draft.json`; that metadata is the authoritative
applyability contract, while `notes.md` is informational. Unsupported edits
still fall back to `var/drafts/import-*/patch.diff` with
`apply_status: review_diff_only`.

Project proposal artifacts must use `project-ops`. Unsupported legacy patch
formats fail fast instead of being interpreted heuristically.

Project-scoped review packs default to `var/reviews/projects/<slug>/` so they do
not collide with variant-level review packs.
