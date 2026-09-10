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
command does not perform free-form NL rewriting of your SoT. Input preflight
checks the source, variant catalog, selected variant, and local job-file kind
before creating a workspace. If guidance fails after creation, it discards the
partial project and active proposal, reporting any cleanup failure explicitly.

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

## Manifest identity and readiness

`project.yaml` is UTF-8 YAML with a `project` mapping. Its `id` and
`base_variant` are required strings matching `[A-Za-z0-9][A-Za-z0-9._-]*`.
Identifiers are single components: paths, whitespace, option-like values, and
non-string YAML values are invalid. Project builds validate this identity before
creating a run directory or copying source files.

Workspace inventory reads identity without requiring proposal artifacts. A
project whose proposals were discarded can remain visible in context. A missing,
unreadable, malformed, or invalid-identity manifest appears in `projects.invalid`
instead of aborting the inventory. Explicit project loading raises `ProjectError`
with an actionable message; parser diagnostics do not echo manifest contents.

Executable project loading additionally requires `sot_path` and the proposal
variant and patch files. Detailed inspection uses one manifest read for both
identity and descriptive metadata. This does not snapshot proposal files.
Descriptive fields follow the contract below; successful identity inspection
alone does not establish build or review readiness.

### Descriptive metadata

Detailed inspection parses descriptive fields into typed records owned by
`manifest.py` and `records.py`, then combines them with proposal/patch state.
It requires:

- `created_at`: an ISO 8601 timestamp with a timezone. Quoted strings and native
  YAML timestamps are accepted; date-only, naive, null, and non-time values are
  rejected. Valid timestamp text retains its existing presentation.
- `job.source.type`: `file` or `url`; `job.source.value`: a nonempty string
  recording the source. This provenance value does not trigger a read or fetch.
- `job.extracted_hash` and `signals.hash`: recorded SHA-256 digests, each with
  64 hexadecimal characters. Format validation does not verify current file
  contents or establish artifact freshness.
- `job.extracted_path`, `signals.path`, and optional `job.raw_path`: nonempty
  artifact paths. Omission/null means no raw artifact; other false-valued inputs
  are invalid. Paths resolve within the owning project directory, including
  symlink resolution. Absolute references inside that directory remain valid;
  traversal and symlinks to outside artifacts are rejected before guidance reads.

Recorded artifact paths and digests describe the stored job context. Parsing
does not require every recorded artifact to still exist or compare its bytes
with the recorded digest. Filesystem changes after path resolution remain a
separate input-lifetime concern. The explicitly selected SoT and original job
source may be outside the project; they are distinct from project-owned artifacts.

`load_project_summary` returns a typed `ProjectSummary` for inventory. It requires
valid identity and validates any displayed creation-time/source fields that are
present, without requiring the complete descriptive record or proposal files.
Missing fields remain unknown. Malformed displayed values become `None` with
field-specific `metadata_errors`; the project remains visible. Full inventory
items carry these diagnostics, and full/compact context includes
`metadata_error_count` when they exist. This count concerns displayed metadata,
not complete project validation or review readiness.

## Creation preflight

File and URL creation validate their local inputs before creating directories.
They share the project identity validator with manifest loading, require an
existing SoT directory, validate the selected base variant with the normal
variant schema, and check the prospective registration's lifetime, cleanup
boundary, and registry eligibility. URL creation performs these checks before
fetching. The registration contract belongs to
[variant lifecycle](variant-lifecycle.md#registration-preflight).

Only an omitted/`None` slug derives an ID from the job filename or URL. Explicit
values must be strings that normalize to the documented project identifier
alphabet; empty or malformed values fail instead of choosing another ID.
Local job input must be a regular file containing readable UTF-8 text. Variant
YAML/encoding errors identify the file without echoing its contents.

The selected variant is parsed once before staging; its validated definition,
including extension metadata, supplies the proposal. Local job text is also
captured before staging and supplies both the extracted text and job signals.
These are separate input captures, not a snapshot of all source files. Direct
creation checks the SoT directory's kind; full source-content validation remains
the responsibility of guidance and build. Registry preflight reserves nothing,
so registration rechecks current eligibility and can still require recovery.

## Mutation recovery

File and URL creation share one staging, publication, and registration lifecycle
in `creation.py`. On failure, cleanup targets the staging directory until rename
succeeds, then the published directory. It compares the directory's device/inode
identity with the original staging directory before deletion. An observed
replacement is left intact and reported alongside the original failure. Cleanup
errors are reported rather than ignored; cancellation retains the interrupt and
adds a note if cleanup also fails.

This ownership check does not provide exclusive creation or isolation from
concurrent filesystem changes. It does not prevent every race between checking
identity and deletion, or reserve the destination against an empty directory
appearing before rename. Input preflight does not guarantee future filesystem
writes will succeed.

`retarget_project_variant` uses one validated manifest read and captures the
proposal bytes from which it obtains the proposal ID. It preserves manifest
extension fields and returns the `ProjectSpec` it wrote rather than rereading
possibly newer metadata after completion. Malformed proposal YAML/encoding and
variant-schema failures surface as `ProjectError` without YAML source snippets.

The operation stages proposal and manifest writes together using
`ops.atomic.replace_files_atomically`, passing their original bytes through
`expected_contents`. The helper checks those bytes before staging and again
before the first replacement. An observed edit or deletion aborts replacement
and preserves the editor's files. In the shared helper, an expected value of
`None` requires an absent destination; an empty file or dangling symlink is not
absent.

An ordinary I/O failure during replacement restores the prior files. If
restoration fails, the error reports incomplete rollback and retained
recovery-backup paths. Replacement failures retain their cause through
`ProjectError`. Byte checks do not lock out concurrent writers or provide
simultaneous multi-file visibility. Edits after the final check, cancellation,
process termination, and a snapshot across all source files remain outside
this recovery contract.

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

Reviewed Experience bullets and Projects summaries can produce this same
`project-ops` schema when edits map to stable SoT IDs. See the
[content-review contract](review-contract.md) for baseline identity, review
bundle locations, import selection, and `draft.json` applyability states.

Project proposal artifacts must use `project-ops`. Unsupported legacy patch
formats fail fast instead of being interpreted heuristically.

## Saved guidance

`job/proposal-plan.json` records the recommendations and selection made when
guidance was generated. Retargeting preserves that evidence. `project show`
and preview compare its recorded `applied_variant` with the current manifest's
base variant through the shared workspace guidance owner.

An optional `proposal_plan_warning` reports a different recorded selection or
a missing/invalid applied variant. It appears in JSON inspection, plain/rich
summaries, and the preview warning area. Read, encoding, and JSON-format errors
appear as `proposal_plan_error`, allowing the remaining project information to
remain available. Diagnostics identify files without echoing their contents.

`load_project_plan(details)` in the project inspection owner derives the optional
plan location beside the recorded signals artifact and checks that the resolved
plan itself stays within the project. Both the CLI and preview use this read API;
they do not derive and read artifact paths independently. Internal symlinks are
valid; a symlink to an outside plan produces `proposal_plan_error` before reading
its contents. An absent plan is optional and produces no error. This check does
not isolate the read from filesystem changes after path resolution.

This comparison concerns the recorded variant selection only. Matching IDs do
not establish freshness of the job, source facts, or variant catalog; review
the recommendations against current evidence before applying content changes.

## Guidance API

`cvworkbench.ops.projects.guide_project` is the callable owner of the guide
workflow. It accepts exactly one `job_file` (`Path`) or `job_url` (`str`), a
workbench `config_path`, and optional `slug`, `variant_id`, `sot_path`, and
`store_raw` selections. An explicit variant is preserved; otherwise the top
eligible recommendation determines the proposal's base variant.
Only omission or `None` selects the configured default; an empty or malformed
explicit variant is rejected instead of selecting another lane.

```python
from pathlib import Path
from cvworkbench.ops.projects import guide_project

result = guide_project(
    config_path=Path("config/workbench.yaml"),
    job_file=Path("job.txt"),
)
project_dir = result.paths.project_dir
proposal_plan = result.proposal_plan
```

The `ProjectGuideResult` contains artifact paths, source tag counts, job evidence,
the variant catalog and recommendations, applied/proposal identifiers, and the
stored proposal plan. The operation emits no terminal output and starts no
preview server. The CLI adapts this result to its existing JSON/plain summaries
and handles optional preview launch.

`config_path` accepts a `Path` or explicit `ConfigSnapshot`. One captured settings
generation controls source selection, project creation, retargeting, registration,
and failure cleanup. Returned `config_path` is an ordinary path for subsequent
commands; those commands select their own settings generation. Source facts,
variant files, and job artifacts have separate reads; this is not a global input
snapshot or a transaction across every project artifact.

Operational failures raise `ProjectGuideError`, a `ProjectError` with individual
diagnostics in its `errors` tuple. Source validation preserves all reported
errors. Invalid catalog/selected-variant and local job-file inputs fail before
project creation. Failures during guidance, retargeting, or plan writing discard
the project and its active proposal; the registry can retain its discarded
record. A cleanup failure adds a diagnostic alongside the original failure.
Cancellation performs the same cleanup while preserving the interrupt. See
[mutation recovery](#mutation-recovery) for the narrower direct-operation
guarantees and their concurrency and termination limits.

## Python Ownership

`cvworkbench.ops.projects` is the public operation surface. Implementations live
under that package, and its entrypoint explicitly exports the callable APIs.
Internal modules import concrete owners rather than the public entrypoint.

| Responsibility | Owner beneath `ops/projects/` |
| --- | --- |
| Artifact, summary, typed metadata records, patch vocabulary, timestamps | `records.py` |
| Project identity validation, selectors, and proposal identities | `identity.py` |
| Manifest reading, typed metadata validation, and executable prerequisites | `manifest.py` |
| Descriptive/proposal inspection and bounded saved-plan reads | `inspection.py` |
| Creation preflight, captured inputs, retargeting, registration, and discard | `creation.py` |
| Guarded edit authoring, compilation, and application | `patches.py` |
| Job evidence, variant ranking, and proposal plans | `guidance.py` |
| Guided creation, preflight, result records, and recovery | `workflow.py` |

Catalog loading is shared through `cvworkbench.variants.load_variants_from_config`.
Workspace modules own inventory and optional-plan presentation. Project
operations do not import workspace, CLI, or preview presentation. The guide
adapter delegates to `guide_project`; terminal summaries and optional preview
launch remain in the CLI. Other project adapters retain their own extraction
boundaries.

`cvworkbench.ops.projects.load_project_metadata` owns manifest reading and
delegates project identity validation to `identity.py`.
`load_project_summary` adapts that read into the partial inventory contract;
`load_project` adds executable-project prerequisites, and `load_project_details`
adds typed descriptive and proposal information from the same manifest generation.
`load_project_plan` reads optional saved guidance from those details, returning
the plan or a diagnostic while leaving the rest of inspection available.

Review implementation boundaries are owned by
[Content Review](review-contract.md#python-ownership). Project patch compilation
and guarded SoT application remain project operations.
