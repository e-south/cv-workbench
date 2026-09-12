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
  renders use the [preview-owned directory](preview-contract.md#artifact-ownership)
  for that project and invocation. When `--sot-path` points at a concrete version directory, preview stays pinned to that exact directory. The
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

### Project selectors

A bare string such as `research` is an ID within the configured project store.
A same-named directory in the caller's working directory does not override that
mapping. Use `./research` to select that local directory explicitly. Absolute
paths, `.`, `..`, and strings containing path separators are explicit paths;
relative paths resolve from the caller's working directory even when missing.
Python `Path` arguments always describe paths, including `Path("research")`.
Empty strings and malformed IDs raise `ProjectError`; CLI adapters report the
error on stderr and exit with code 1 before writing project or build artifacts.

Generated project commands preserve the selected directory and configuration.
They use the ID only when its configured mapping selects that exact directory;
otherwise they use a shell-quoted absolute path. Plain and JSON creation
summaries consume the same command descriptions. Commands describe current
selection, not a filesystem reservation: later moves or replacement can invalidate
them. Project run and review namespaces remain ID-scoped within the selected
configuration; copying a manifest does not create an independent run identity.

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

The manifest must resolve to a regular file within its project directory.
Manifest reads reject external symlinks and non-regular inputs before opening
them. These checks do not lock out concurrent filesystem changes.

Workspace inventory reads identity without requiring proposal artifacts. A
project whose proposals were discarded can remain visible in context. A missing,
unreadable, malformed, or invalid-identity manifest appears in `projects.invalid`
instead of aborting the inventory. Explicit project loading raises `ProjectError`
with an actionable message; parser diagnostics do not echo manifest contents.

Executable project loading additionally requires `sot_path` and the proposal
variant and patch files. Detailed inspection resolves their recorded locations
without requiring those files, then reports proposal availability separately.
It uses one manifest read for both identity and descriptive metadata. This does
not snapshot proposal files.
Descriptive fields follow the contract below; successful identity inspection
alone does not establish build or review readiness.

### Descriptive metadata

Detailed inspection parses descriptive fields into typed records owned by
`manifest.py` and `records.py`, then combines them with independently observed proposal/patch state.
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

`load_project_details` requires the descriptive record, but it does not require
available proposal files. Its `ProjectDetails.proposal_issues` contains typed
`ProjectProposalIssue` records, and unavailable proposal values are `None`.
`proposal_available` means both files could be loaded under their existing
schemas; it does not validate patch targets against current source content.
See [project inspection](project-inspection.md#proposal-availability-and-retained-history)
for output fields, diagnostics, and conditional command descriptions.

### Artifact inspection

`cvworkbench.ops.projects.inspect_project_artifacts(project_dir)` compares the
stored extracted text and signals file with their recorded SHA-256 values.
It returns two `ProjectArtifactCheck` records without requiring retained
proposal files or opening the original job source. Each record includes its
name, path, recorded/observed digests, state, and optional read diagnostic:

| State | Meaning |
| --- | --- |
| `matches_record` | The observed file bytes match the manifest's recorded digest. |
| `changed` | The observed bytes differ from the recorded digest. |
| `missing` | The stored artifact cannot be found. |
| `unreadable` | The artifact is not a regular file, cannot be read, or fails the ownership recheck. |

Manifest errors still raise `ProjectError`. Artifact failures are observations,
not reasons to hide otherwise inspectable project details. `load_project_details`
includes these records in `artifact_checks`, using its already parsed manifest
metadata. Inventory remains lightweight and does not hash job artifacts.
Checks stream file bytes and recheck project ownership before reading. They do
not isolate concurrent changes after resolution or guarantee a filesystem snapshot.

`project show --json` includes `job_artifacts`, a shared `job_artifact_status`,
and `job_artifact_warning` when files need review. Plain/rich output and preview
show the same summary and warning. Preview caches the checks from its last
successful rebuild; status polling does not hash the files again. Job-file edits
alone are not watched, so rebuild to refresh those observations.

These comparisons concern the current manifest's records, not authenticated
provenance or an immutable record of the saved plan's inputs. Editing both a
file and its recorded digest can yield a match. Optional raw captures have no
recorded digest and are not checked here. Matching job files do not establish
freshness of the original source, source facts, variant catalog, saved guidance,
or build output. Review readiness continues to describe the selected immutable
run's available review inputs; it is independent of this job-artifact check.

## Project build API

```python
from pathlib import Path
from cvworkbench.ops.projects import build_project

result = build_project(
    "research",
    config_path=Path("config/workbench.yaml"),
    formats=["md", "pdf", "docx"],
)
```

This operation owns `build --project`. It accepts the shared project selector,
a configuration path or `ConfigSnapshot`, and optional `sot_path`, `theme`, and
`style_preset` overrides. The proposal owns variant selection. The operation
captures one configuration generation for project/source resolution, run
placement, content selection, and render choices, and prints nothing.

Guarded edits are prepared in a temporary source copy. Source schema validation,
variant/content selection, format normalization, filter resolution, render
planning, rendering, and metadata collection complete in temporary directories
before a persistent project run is allocated. Preflight, render, and metadata
errors leave the workspace unchanged and release temporary preparation. An
explicit source override selects that source instead of the manifest's active
version.

The returned `BuildResult` exposes `run_dir`, `dist_dir`, `canonical_path`, the
selected variant, formats, theme, and preset. Both artifact destinations are the
allocated `<runs-root>/projects/<id>/<run-id>/` directory. A nonempty patch's
prepared source is retained in that run's `sot/`; an
empty patch uses the selected source directly. The operation does not modify the
source or project, publish output, or start a preview.

`building.py` captures the completed run's files and directory permission bits
before allocation. It retains outputs and prepared source through one
recoverable file group, including empty source directories. File and directory
permission bits survive retention; this is not an archival copy of all filesystem
metadata. Manifests follow other files in the commit order. Returned paths refer
to the persistent run, never the released temporary workspace.

`ProjectBuildError.errors` preserves individual source-validation diagnostics;
the CLI prints each on stderr and exits with code 1 without partial JSON. Other
selection, configuration, preparation, and renderer exceptions retain their
domain types for Python callers and become CLI errors. The shared
`build/runs.py::allocate_run` owns exclusive timestamp/suffix allocation and
failure cleanup for both ordinary and project builds. Storage recovers file
writes, then allocation removes only still-owned empty run/parent directories.
Existing history, independently written files, and replacement directories are
preserved. A retained directory is named in exception notes and CLI stderr.
Cancellation preserves its exception type. Recovery failures retain evidence;
no writer locking, simultaneous reader visibility, or crash durability is
promised. See the shared
[bundle recovery contract](configuration-contract.md#build-bundle-recovery).
Configuration capture does not freeze every source, variant, and theme file; see
[build planning and input lifetime](configuration-contract.md#build-and-render-boundaries).

## Source preparation

`cvworkbench.ops.projects.prepare_project_sot(project_dir=..., sot_path=...,
target_dir=...)` compiles the project's guarded edits against an existing source
directory. An empty patch returns the resolved source path without creating or
replacing the destination. A nonempty patch requires a fresh destination outside
both the source and project directory trees. Neither an ancestor nor a descendant
is allowed; checks use resolved paths and reject existing files, directories,
and destination symlinks.

The operation exclusively creates the destination before copying source files
and applying the compiled patch there. The source and project remain unchanged.
It returns the prepared directory; it does not render, publish, or declare full
source-schema validity. Build and preview retain their content-validation gates.

On a copy or patch failure, cleanup compares the destination's device/inode
identity with the directory this call created. An observed replacement is left
intact, and any cleanup error accompanies the original failure. Cancellation
retains the interrupt and attempts the same owned-directory cleanup. Parent
directories created along the destination path may remain. These checks are not
a filesystem transaction and do not prevent every concurrent replacement race.

Builds use a fresh run-local destination. Preview owns a temporary directory for
each rebuild and releases it after success or failure; it does not refresh a
shared staging directory in place. Existing historical staging directories are
outside this operation's cleanup ownership.

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
`storage.replace_files_atomically`, passing their original bytes through
`expected_contents`. The helper checks those bytes before staging and again
before the first replacement. An observed edit or deletion aborts replacement
and preserves the editor's files. In the shared helper, an expected value of
`None` requires an absent destination; an empty file or dangling symlink is not
absent.

An ordinary I/O failure during replacement restores the prior files. If
restoration fails, the error reports incomplete rollback and retained
recovery-backup paths. Replacement failures retain their cause through
`ProjectError`. Byte checks do not lock out concurrent writers or provide
simultaneous multi-file visibility. Cancellation during replacement also attempts
rollback and retains its original exception type; incomplete recovery is attached
as an exception note. Edits after the final check, forced process termination,
repeated interruption during recovery, and a snapshot across all source files
remain outside this recovery contract.

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

The [patch application contract](patch-application.md) owns unified-diff
execution, captured target inputs, source-write recovery, and file permissions.
The same executor handles explicit application and temporary source preparation;
project operation compilation retains the stable-target checks described here.

### Proposal authoring

`patch_authoring.py` owns the two append APIs exposed by
`cvworkbench.ops.projects`. `patches.py::read_project_patch_document` captures
the proposal bytes and parsed payload from one read; the same owner compiles
operations and validates stable targets against the current source.

Authoring validates the destination, proposal, and complete candidate operation
list before creating a lock file. Invalid UTF-8, malformed YAML, unsupported
formats, missing targets, and stale source guards become `ProjectError`
diagnostics without changing the proposal or creating a lock. Proposal writes
must stay inside the project and target a regular, non-symlink file. Lock files
must be regular, non-symlink files with a single filesystem link.

Cooperating writers serialize through a thread mutex and filesystem lock, then
reread and validate the locked proposal generation. Saving uses `storage.py`
with the captured bytes as `expected_contents`: an observed intervening edit or
deletion fails instead of overwriting or recreating that proposal. Unknown
metadata, the original `created_at`, and existing file permissions are retained;
`updated_at` records the append. I/O failures use the shared recoverable write
path; cancellation preserves its exception type. Source files are unchanged.

Once created, `proposals/patch.yaml.lock` remains in place so cooperating writers
use a stable lock inode; its initial permissions are `0600`. Do not delete it
while authoring may be active. A failed locked operation may leave this lock
file even though the proposal remains unchanged.

This is cooperative serialization and recoverable saving, not a source lock,
crash-durability guarantee, or protection from every filesystem race. The
[shared recovery contract](configuration-contract.md#build-bundle-recovery)
describes failure restoration and retained recovery files. The
[patch application contract](patch-application.md) separately owns applying
accepted edits to source files.

Verification: `tests/ops/test_project_patch_authoring.py` covers interrupted
saves, independent edits and deletions, invalid inputs, aliased paths, metadata
and permissions, real subprocess locking, and CLI diagnostics.

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

New plans also record versioned input fingerprints. Inspection distinguishes
matching inputs, known changes, and unverifiable provenance; old plans remain
readable. The [guidance provenance contract](guidance-provenance.md) owns the
component definitions, public inspection API, and comparison limits.

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
| Job-byte capture and stored-file observations against recorded digests | `artifacts.py` |
| Descriptive/proposal inspection and bounded saved-plan reads | `inspection.py` |
| Creation preflight, captured inputs, retargeting, registration, and discard | `creation.py` |
| Proposal byte/payload reads, guarded compilation, and application | `patches.py` |
| Candidate validation, cooperative locking, and recoverable proposal saves | `patch_authoring.py` |
| Source preparation in a fresh owned directory and failure cleanup | `preparation.py` |
| Project build preflight, source validation, retained-run orchestration | `building.py` |
| Job evidence, variant ranking, and proposal plans | `guidance.py` |
| Saved guidance input fingerprints and comparison | `provenance.py` |
| Guided creation, preflight, result records, and recovery | `workflow.py` |

Catalog loading is shared through `cvworkbench.variants.load_variants_from_config`.
`cvworkbench.workspace.projects` owns inventory, command descriptions, and shared
full/preview inspection; see its [inspection contract](project-inspection.md).
Project operations do not import workspace, CLI, or preview presentation. The guide
adapter delegates to `guide_project`; terminal summaries and optional preview
launch remain in the CLI. The show adapter delegates to `inspect_project`.
Other project adapters retain their own extraction boundaries.

`cvworkbench.ops.projects.load_project_metadata` owns manifest reading and
delegates project identity validation to `identity.py`.
`load_project_summary` adapts that read into the partial inventory contract;
`load_project` adds executable-project prerequisites. `load_project_details`
instead combines typed descriptive information with proposal availability from
the same manifest generation, preserving retained history when proposals expire.
Artifact observation is callable independently through `inspect_project_artifacts`;
the same owner supplies `ProjectDetails.artifact_checks`.
`load_project_plan` reads optional saved guidance from those details, returning
the plan or a diagnostic while leaving the rest of inspection available.

Review implementation boundaries are owned by
[Content Review](review-contract.md#python-ownership). Project patch compilation
and guarded SoT application remain project operations.
