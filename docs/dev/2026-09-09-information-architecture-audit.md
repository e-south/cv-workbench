# CV Workbench information architecture audit

Date: 2026-09-09. Scope: local checkout, authored CV preparation, generated
build/review journeys, preview HTTP boundary, documentation, packaging, and
artifact lifecycle. The personal site and canonical private CV master were not
changed. Each finding distinguishes completed fixes from proposed next work.

## Decision

The engine already separates structured inputs, rendering, and site sync. Its
main weakness is that the operator-facing model does not expose those boundaries
consistently. In particular, generated resumes and authored CV publications
share vocabulary while following different source and review contracts.

Prioritize portable resources and publication discovery, then split modules by
their existing responsibilities. Keep current command names during internal
extraction; any public command or artifact migration needs its own reviewed
contract. A framework change is not needed to address the observed failures.

## Current authority map

| Information | Authority | Derived output / consumer |
| --- | --- | --- |
| Structured facts for tailoring | Configured private YAML profile | Selected Markdown, generated resumes, cover letters |
| Wording and layout of the authored public CV | Private editable DOCX and its authoring-app PDF export | Sanitized public PDF |
| Public contact allowlist and disclosure rules | Configured person data, publication policy, selected variant | Preparation and sync validation |
| Generated artifact provenance | Build run manifest and selection record | Explain, review/import, comparison |
| Public artifact provenance | Authored publication manifest | Public PDF review and sanitized site manifest |
| Website presentation | Personal site | View/download the validated PDF |

The YAML profile is not currently the content authority for the authored DOCX.
Editing YAML or using ordinary `preview` does not update the public CV. Present
these as explicit product journeys and avoid suggesting one global editable
source of truth.

## Findings and disposition

### High for source integrity — patch application used live temporary files and partial mutation — fixed

`ops/patches.py` wrote `.cvw.patch.tmp` inside the selected source directory and
unconditionally removed that filename afterward. Isolated tests reproduced loss
of an existing file and overwriting an unrelated file through a symlink. The
file-based entrypoint validated text from one read but then gave the external
tool the original mutable patch path, allowing a later edit to change execution.
Both dry run and real application operated on live source files; a change after
dry run or interruption after writes could leave partial edits and reject files.
Six regressions failed for these boundaries
(`/tmp/cvw-patch-application-red.log`).

The shared executor now captures patch text, target bytes, and source permission
bits; runs both tool phases against temporary copies; and commits completed
outcomes through shared storage with original-byte preconditions. Project
application, draft application, and project source preparation share this owner.
Temporary/reject files stay outside the live source directory. The text entrypoint
accepts text alone; the ambiguous optional `patch_path` argument was removed from
its sole repository caller. File-based application reads UTF-8 bytes once and
delegates to that text entrypoint. No compatibility alias was added.

Storage now supports explicit file deletions in the same recoverable group as
replacements. Five initial contract tests defined successful mixed changes and
recovery before/after an interrupted deletion. Follow-up checks cover conflicting
roles, directories, symlinks, observed edits, permission preservation, and a
retained deletion backup when restoration itself fails. Evidence:
`/tmp/cvw-patch-storage-delete-red.log` and
`/tmp/cvw-patch-storage-delete-green.log`.

The parser now counts unified hunks instead of treating header-like document
text as additional filenames. Eleven follow-up regressions covered that parsing
failure, valid identical replacements, malformed grammar reaching tool discovery,
and untyped/unreadable input (`/tmp/cvw-patch-grammar-red.log`). Matching headers,
regular targets, explicit creation/deletion, no parent traversal, and no duplicate
targets form the supported input contract. Renames, arbitrary preambles, and
other patch formats fail closed. The tool runs noninteractively with fuzz
disabled. These are deliberate input-contract changes, not a claim of preserving
every input accepted by the earlier permissive scanner.

A regression in the new staging implementation initially widened newly created
source-file permissions under a private umask. It was caught before commit and
fixed by retaining the tool-created mode; existing files retain their captured
permission bits (`/tmp/cvw-patch-permissions-red.log`).

The focused suite passed 133 tests. The full suite passed 1,020 tests with one
opt-in skip and five existing PyMuPDF/SWIG warnings in 99.23 seconds
(`/tmp/cvw-patch-application-full.log`). Seven standard CLI journeys passed with
zero exit codes and empty stderr. A separate five-step CLI journey authored an
edit, built the project, applied the edit, rebuilt ordinary output, and rejected
a stale second application. Only the intended source file changed; proposal
artifacts and an existing operator-owned `.cvw.patch.tmp` were preserved
(`/tmp/cvw-patch-application-operator.json`).
Final repository/documentation/import contracts passed 30 tests. Ruff and all
pre-commit checks, including the secret scan, passed
(`/tmp/cvw-patch-application-final-contracts.log`,
`/tmp/cvw-patch-application-hooks.log`). The slice's TDD handoff gate is `pass`.

All 8,317 live private entries retained their recorded metadata, master/candidate
hashes remained unchanged, and the site stayed clean and untouched
(`/tmp/cvw-patch-application-live-preservation.json`). The candidate remains
`review_required`. The new [patch application reference](../reference/patch-application.md)
is routed from project/review contracts, shared storage documentation, the docs
index, and scoped operations instructions. It states the limits: per-input
capture and recoverable writes do not establish locking, simultaneous reader
visibility, crash durability, or an external-tool sandbox.

This source-mutation finding took priority over patch-authoring decomposition.
Proposal append still uses direct `write_text` under its cooperative authoring
lock; atomic proposal replacement and whole-request configuration/source-version
selection remain follow-up work. The broader audit remains active.

### High for run integrity — failed project builds retained incomplete source/run history — fixed

The outer project operation allocated a persistent run and moved its prepared
source into that run before rendering and metadata collection. The shared build
pipeline recovered its own output group, but did not own the already-retained
project source or run directory. Four real Lua-filter regressions reproduced
this through Python and CLI, with both empty and nonempty patches: failed builds
left new directories, and tailored builds also left their copied source
(`/tmp/cvw-project-recovery-red.log`). The criterion is that preflight, render,
and metadata failures create no persistent project run.

`ops/projects/building.py` now executes the entire build in temporary directories
and captures its completed files before reserving a persistent run. Documents,
metadata, and prepared source are retained through one shared storage group.
Returned paths point to the retained run. The existing public build API, CLI
flags, project hierarchy, and timestamp/suffix naming remain unchanged.

Four commit-failure tests, before/after the final manifest replacement with both
I/O errors and cancellation, then exposed empty project-parent directories left
behind (`/tmp/cvw-project-recovery-commit-red.log`). `build/runs.py::allocate_run`
now owns exclusive allocation and cleanup for ordinary and project builds.
It removes only still-owned empty directories, including newly created parents.
Existing history, replacement directories, independent files, and unrecovered
evidence survive. The internal pipeline allocator was removed; callers and its
collision test use the new owner directly, without a compatibility alias.

A separate regression proved that the CLI omitted exception notes identifying
a retained run containing an independently written file. Build errors now print
those notes on stderr (`/tmp/cvw-project-recovery-diagnostics-red.log`). Python
callers retain the domain exception; cancellation retains its original type.

Validation of the new retention implementation caught a permission regression
before commit: recreating only files widened a private source directory and
omitted empty directories. Storage now accepts an explicit `new_directories`
mapping for absent directories, initially creates them owner-only, and applies
recorded permission bits after file writes. Failed mode application participates
in recovery. Existing directories, symlinks, duplicate paths, file-role
collisions, invalid modes, and non-mapping inputs fail closed. File and directory
permission bits and empty source directories survive retention; archival
filesystem metadata is outside this contract. Evidence:
`/tmp/cvw-project-recovery-permissions-red.log` and
`/tmp/cvw-project-recovery-directory-contract-red.log`.

The final focused suite passed 86 tests, including ownership replacement,
foreign-file preservation, source permissions, mode failure, and previous-run
preservation after metadata failure. The full suite passed 981 tests, with one
opt-in skip and five existing PyMuPDF/SWIG warnings in 97.07 seconds
(`/tmp/cvw-project-recovery-full.log`). All seven standard CLI journeys passed
with zero exit codes and empty stderr. A separate tailored-project journey built
Markdown, PDF, DOCX, and HTML, then produced a review pack while preserving
source/proposal/run fingerprints and source permissions
(`/tmp/cvw-project-recovery-operator.json`).
Final repository/documentation/import contracts passed 29 tests. Ruff and all
pre-commit checks, including the secret scan, passed
(`/tmp/cvw-project-recovery-final-contracts.log`,
`/tmp/cvw-project-recovery-hooks.log`). The slice's TDD handoff gate is `pass`;
the broader product audit remains active.

All 8,317 private entries retained their recorded metadata; master/candidate
hashes were unchanged (`/tmp/cvw-project-recovery-live-preservation.json`).
The site remains clean and untouched, and the public candidate remains
`review_required`. The live [project build API](../reference/project-contract.md#project-build-api)
and [shared recovery contract](../reference/configuration-contract.md#build-bundle-recovery)
own the guarantees and limits. This is recoverable file replacement, not writer
locking, simultaneous visibility to readers, or crash durability. External tools
remain trusted; their independent side effects are outside run recovery.

### High for artifact provenance — rendering could outlive recorded inputs — fixed within explicit lifetime checks

Theme definitions, templates, defaults, styles, and selected Lua filters could
change or disappear after planning while the build committed outputs paired with
earlier hashes. Theme parsing and fingerprinting also read separate generations.
An explicitly empty filter selection silently rediscovered filters from disk.

`build/assets.py` now owns an immutable fingerprint record and checks explicit
asset lifetimes before output allocation and after staged generation, before the
bundle commits. `themes.py` owns composite-hash membership/order and fingerprints
the exact definition bytes it parses. Planning rejects observed inconsistencies;
execution rejects observed changes, deletions, and unrecorded asset selections.
Previous output bundles survive failures. Existing paths and hash encodings are
preserved. Build manifests add ordered filter names and SHA-256 fingerprints;
historical missing provenance remains unknown. An empty filter list now means
no filters, including when files appear after planning.

The initial regression log reproduced 15 asset-lifetime failures. The corrected
known-filter fixture separately reproduced both empty-selection failures; its
first unsupported filename was not valid evidence of that bug. Three further
negative cases exposed unrecorded template/defaults selections and inconsistent
style hashes. The final asset suite covers 23 cases using isolated inputs and
real rendering, with narrow observers for changes during planning/rendering.
Evidence: `/tmp/cvw-render-assets-red.log`,
`/tmp/cvw-render-assets-filters-red.log`, and
`/tmp/cvw-render-assets-selection-red.log`.

These checks enforce observed lifetimes, not immutable asset snapshots. A change
reverted between checks or made after the final check can escape detection.
Indirect template/defaults dependencies, Lua modules, fonts, user data, and
external processes are not a frozen dependency graph. The current authority is
the [render-asset contract](../reference/configuration-contract.md#render-asset-lifetime).
Full reproducible asset packs require an explicit dependency contract before
copying or relocating assets.

### Medium for workflow availability — metadata probed an unused or incorrect PDF engine — fixed

Metadata collection probed the configured PDF engine even for Markdown, HTML,
DOCX, and ATS builds. It also ignored a PDF theme route's engine override. Five
real builds failed on an unavailable configured executable, including a PDF
successfully rendered by the theme-selected engine
(`/tmp/cvw-render-assets-engine-red.log`). `BuildPlan.pdf_engine` now records the
effective PDF route engine, or `None` when PDF is not selected. Rendering and
manifest tool metadata agree; non-PDF formats avoid the unused probe.

The focused suite passed 193 tests. Repository/documentation contracts passed 28;
the full suite passed 953 with one opt-in skip and five existing PyMuPDF/SWIG
warnings in 94.57 seconds (`/tmp/cvw-render-assets-full.log`). The isolated
seven-step CLI journey passed with zero exit codes and empty stderr, including
preserved audited artifacts after preview
(`/tmp/cvw-render-assets-journey.json`). All 8,317 private entries retained their
recorded metadata, and master/candidate hashes remained unchanged
(`/tmp/cvw-render-assets-live-preservation.json`). Publication remains
`review_required`; the personal-site checkout remains clean and untouched.
Ruff and all pre-commit checks, including the secret scan, passed
(`/tmp/cvw-render-assets-hooks.log`). Final documentation/import contracts passed
28 tests after this audit record was added.

### High for artifact ownership — previews overwrote audited and shared outputs — fixed

Ordinary preview rendered into configured `var/dist/<variant>/` with audit
artifacts disabled. A changed source/style therefore replaced documents and CSS
while leaving the preceding build manifest and selection unchanged. Independent
controllers for the same variant or project also shared output locations.
Project canonical input lived in the static HTTP directory.

`dev/preview_paths.py` now owns invocation-scoped paths under the preview tree,
with separate variant/project scopes and `input/` versus `output/` directories.
Each controller generates its own opaque filesystem identity, independent of its
browser control lease. Rebuilds reuse that controller's directory; independent
invocations preserve each other's last successful preview. Only rendered output
is the HTTP root. CLI fields and HTTP filename maps remain the discovery surface;
callers/tests now consume returned paths instead of reconstructing legacy paths.
No legacy preview folders were moved, read as fallback, or removed.

Source validation occurs before persistent preview allocation. A real failing
Pandoc Lua filter also exposed an uncaught `RenderError`; preview now translates
render/I/O failures through `PreviewError`, preserves previous artifacts and
build id, and records `last_error`. Existing HTTP error handling returns the
normal failed-render response. Live HTTP checks return 404 for canonical input
and traversal attempts while continuing to serve the HTML and linked CSS.

Harness setting: repository-local code and generated artifacts. Selected lane:
`autonomy-hardening`; endpoints: `architecture-invariants` for artifact ownership
and `knowledge-integrity` for path/retention routing. The target is a deterministic
ownership check for this workflow, not a whole-product maturity claim. The
workflow-router, operational endpoints, evidence checks, maturity, change-pattern,
and validation-loop references were used. No external claims or provider refresh
were needed. No clarification or publication authorization was requested.

| Criterion / threshold | Before | Preventive check and result |
| --- | --- | --- |
| No audited-output changes, controller collisions, or served canonical input | Four real-render regressions failed | `tests/dev/test_preview_outputs.py`: ownership and rebuild cases pass |
| Failed rendering retains the previous preview and reports its error | Real Lua failure bypassed preview error handling | Same module verifies the error and unchanged bundle |
| Reject every preview that returns shared output or changes the preceding build | Harness accepted all three unsafe scenarios | `tests/dev/test_verify.py`: 3/3 rejected before later steps |
| Local journeys preserve audited artifacts without manual repair | Previous harness checked only output existence | Three isolated seven-step runs pass; Markdown/HTML/CSS/canonical hashes match |
| Paths and retention have one current contract | Styling/project docs and seven CLI tests assumed old paths | Live leaves route to preview ownership; repository/fixture/import checks pass |

The harness now captures complete build dist/run file inventories and SHA-256
fingerprints, compares them after preview, validates the returned preview-owned
output path, and records `audited_build_artifacts: preserved`. This changes a
false-green existence check into an ownership check. Evidence:
`/tmp/cvw-preview-ownership-red.log`,
`/tmp/cvw-preview-ownership-errors-red.log`,
`/tmp/cvw-preview-ownership-harness-red.log`,
`/tmp/cvw-preview-ownership-focused.log`, and
`/tmp/cvw-preview-ownership-repeatability.json`.

The focused preview/harness/HTTP suite passed 38 tests, and the broader
contract/workspace/isolation checks passed 152. The full suite passed 924 tests
with one opt-in remote skip and five existing PyMuPDF/SWIG warnings in 90.61
seconds (`/tmp/cvw-preview-ownership-full.log`). Each of the three CLI journeys
passed seven steps with empty stderr. Ruff, the harness skill audit, and all
hooks including the secret scan passed. Protected
`local/` and `var/` inventories retained all 8,317 entries and their recorded
metadata; master/candidate hashes remained unchanged. Publication remains
`review_required`, and the site remains untouched.

The [preview contract](../reference/preview-contract.md#artifact-ownership)
is the current authority. Preview artifacts deliberately survive exit/stop and
remain excluded from build catalogs and run GC. A dedicated preview-retention
plan remains follow-up work; whole-store cleanup is not a preview-only pruning
mechanism. Render-asset capture, configuration capture across an entire preview
request, and the outer project-build lifecycle remain separate boundaries.

### High for artifact integrity — failed builds mixed output generations — fixed

A real Markdown/HTML build with a Lua filter failing only HTML replaced canonical
content, selections, Markdown, and CSS before failing. Previous HTML/manifests
survived beside that new content. Five initial regression cases reproduced this
across shared/separate destinations and audited/unaudited builds, including a
new default run left behind (`/tmp/cvw-build-bundle-red.log`). Per-document
atomic rendering did not establish a coherent build lifecycle.

Bundle membership and temporary generation now belong to `build/artifacts.py`;
`build/pipeline.py` commits completed payloads through the shared lower-level
`storage.py`. Build/input layers retain their one-way import boundary. Captured
resume bytes outlive an abandoned metadata task safely. Default runs are reserved
after rendering and metadata succeed. Existing output bytes serve as optimistic
preconditions, and role collisions fail before output writes. Retained HTML runs
now include their linked CSS. Caller-owned notes and unselected files survive.

Storage now rejects resolved aliases and nonregular destinations, recovers the
attempted file group on cancellation as well as ordinary I/O errors, and removes
only empty directories whose recorded ownership still matches. Recovery failures
retain backups. CLI/preview adapters surface commit failures with their normal
error semantics; preview preserves the previous build id and document.

Additional red checks reproduced cancellation damage, duplicate aliases, missing
run CSS, filename collisions, retained empty directories, shared-directory alias
handling, and uncaught adapter errors. Evidence:
`/tmp/cvw-build-bundle-extended-red.log`,
`/tmp/cvw-build-bundle-final-red.log`, and
`/tmp/cvw-build-bundle-adapter-red.log`. The focused domain suite passed 163 tests;
the storage/build/adapter/import suite passed 100 tests. A final file-symlink
alias regression reproduced a deduplication bypass before that path was rejected
at build preflight (`/tmp/cvw-build-bundle-symlink-red.log`). All 15 bundle cases
then passed (`/tmp/cvw-build-bundle-final-recovery.log`).

The first inclusive run found two existing operation regressions: a refused
replacement incorrectly triggered restoration of an unchanged destination and
retained an unnecessary backup. Recovery now distinguishes an unconsumed staged
file from a completed replacement, retaining cancellation coverage. The 75
storage/build/review/project checks passed afterward
(`/tmp/cvw-build-bundle-rollback-green.log`).

Final verification passed 914 tests with one opt-in remote skip and five existing
PyMuPDF/SWIG warnings in 90 seconds (`/tmp/cvw-build-bundle-final-full.log`). All
seven isolated CLI journeys passed with empty stderr
(`/tmp/cvw-build-bundle-final-journey.json`). Ruff and all hooks, including the
secret scan, passed. The 8,317 protected `local/` and `var/` entries retained their
inventory and recorded filesystem metadata. Canonical master and public candidate
hashes were unchanged. Context remained ready with no issues, publication remained
`review_required`, and the site remained clean. No site sync, publication approval,
push, remote refresh, or external advisory check occurred.

This change provides recoverable file replacement, not a reader-visible atomic
snapshot, writer locking, crash durability, or a renderer sandbox. Unaudited
preview mode does not refresh preexisting audit metadata. Project operations
still own source/run directories they allocate before entering the pipeline.
Render-asset capture and that outer project lifecycle remain separate follow-ups.
The [live contract](../reference/configuration-contract.md#build-bundle-recovery)
is the authority for current guarantees.

### High for source preservation — project preparation replaced existing directories — fixed

`prepare_project_sot` removed an existing destination before copying source
files. Disposable cases confirmed deletion when that destination was the source,
its parent, the project, or an unrelated directory. Descendant destinations also
reached the copying operation without an overlap check. The public preparation
API therefore violated source preservation independently of CLI selection.

Source preparation now has a separate owner, `ops/projects/preparation.py`,
while guarded edit compilation/application stays in `patches.py`. Nonempty
patches require a fresh destination outside source and project trees. Exclusive
directory creation rejects a destination claimed after preflight. Failure
cleanup compares the generated directory's device/inode identity and leaves an
observed replacement intact, reporting the cleanup problem with the original
error. Cancellation retains its interrupt. Empty patches return the source
without allocating a copy. The
[source preparation contract](../reference/project-contract.md#source-preparation)
defines the API, ownership, and concurrency limits.

Preview rebuilds now own a temporary source copy for each render and release it
after success or failure. Real sequential HTML renders pick up changed proposal
text, preserve source bytes, and leave no retained preparation directory. An
injected render failure also releases staging and preserves the previous output.
Historical staging directories are untouched; this change does not authorize
cleanup of preexisting private workspace contents.

Six initial regressions reproduced source/destination damage or missing overlap
guards (`/tmp/cvw-project-preparation-red.log`). Three lifecycle checks reproduced
partial-copy retention, failed-patch retention, and persistent shared preview
staging (`/tmp/cvw-project-preparation-lifetime-red.log`). Replacement-directory
failure evidence is in `/tmp/cvw-project-preparation-ownership-red.log`.
The final focused suite passes 16 cases, including symlinks, cancellation, late
destination claims, replacement ownership, and real preview refresh/cleanup.

The full suite passed 841 tests with one opt-in remote skip and five existing
PyMuPDF/SWIG warnings (`/tmp/cvw-project-preparation-full.log`). All seven isolated
CLI journey steps passed with empty stderr
(`/tmp/cvw-project-preparation-journey.json`). Ruff and the documentation/import
boundary checks passed. The canonical master and public candidate hashes were
unchanged, context reported a ready source with no issues, and publication still
required review. The site remained clean; no network refresh, publication
approval, sync, or push occurred.

### Medium — project build allocated a run before render preflight — fixed

The CLI created a project run before the build pipeline validated render
settings. A real isolated `build --project research --format md --json` with a
missing theme exited with the expected diagnostic but left a new run directory.
The source was unchanged. Evidence: `/tmp/cvw-project-build-preflight-audit.json`.
This violated preflight-before-artifact-write and accumulated incomplete runs.

`ops/projects/building.py::build_project` now owns the same callable workflow
used by the CLI. It captures configuration once, prepares edits temporarily,
validates source data, and constructs a shared build plan before run allocation.
`build/planning.py` owns content/format/render choices; `build/pipeline.py` executes
the plan without repeating those decisions. Nonempty edits retain their prepared
source in the successful run, and project outputs remain run-local. Source and
project input files remain unchanged. The
[project build API](../reference/project-contract.md#project-build-api) is the
operator-facing contract.

Initial CLI regressions for theme, preset, formats, empty formats, and source
validation reproduced persistent writes (`/tmp/cvw-project-build-red.log`). The
tests also cover unsafe variant IDs, stale patch guards, missing letter selection,
individual source diagnostics, and the Python API's retained source/output hashes.
Configuration checks exercise settings edits/removal during preparation and an
explicit captured snapshot. A real planner/executor check proves planning writes
nothing, omits private content from its representation, and preserves captured
settings when the config file disappears. Repeating the original fixture command
now leaves its entire workspace unchanged:
`/tmp/cvw-project-build-preflight-fixed.json`.

A build plan is request-local, not a durable input bundle or publication approval.
The subsequent input-provenance pass captures source and variant fingerprints
with their consumed content. Render assets have a separate lifetime from captured
configuration, and post-preflight filesystem/render failures can retain incomplete
artifacts.

Verification passed 855 tests with one opt-in remote skip and five existing
PyMuPDF/SWIG warnings (`/tmp/cvw-project-build-full.log`). The 31 focused checks
passed, as did all seven isolated CLI journey steps with empty stderr
(`/tmp/cvw-project-build-final-focused.log` and
`/tmp/cvw-project-build-journey.json`). Ruff and documentation/import-boundary
checks passed. Source and public-candidate hashes remained unchanged; context
reported a ready source, no issues, and publication still requiring review.
The site remained clean. No network refresh, publication approval, sync, or push
occurred in this pass.

### Medium — build fingerprints could describe unconsumed inputs — fixed

Build planning parsed source facts, snippets, and a variant before manifest
collection reopened those files during rendering. Editing an input after planning
produced a document from the captured content with a hash of later content.
Deleting it caused a metadata error after output writes; adding an optional YAML
file falsely listed it as consumed. Seven regressions reproduced these failures
in isolated workspaces (`/tmp/cvw-build-provenance-red.log`). The failed criterion
was that recorded input fingerprints identify the content actually used.

Source and variant loaders now own parsing and fingerprinting of the same captured
bytes. A build plan carries that evidence to manifest collection. Duplicate snippet
paths share one captured read, file text retains newline/whitespace normalization,
and inline hashes retain their original parsed-text encoding. Manifest field names
remain stable. Removing the manifest's separate input parser eliminates competing
interpretations of snippet definitions. The
[build input lifetime contract](../reference/configuration-contract.md#build-and-render-boundaries)
defines the per-input guarantee and its limits: nested Python payloads are mutable,
capture is not atomic across all files, render assets are still path-based, and
later rendering/filesystem failures can retain partial artifacts.

Verification passed 868 tests with one opt-in remote skip and five existing
PyMuPDF/SWIG warnings (`/tmp/cvw-build-provenance-full.log`). The 129 focused checks
include mutations during parsing, optional-file changes, exact raw-byte hashes,
inline text, repeated snippet paths, and content omission from snapshot repr.
Evidence: `/tmp/cvw-build-provenance-focused.log`. All seven isolated CLI journey
steps passed with empty stderr (`/tmp/cvw-build-provenance-journey.json`), and 13
documentation/import-boundary tests passed. All pre-commit hooks, including the
secret scan, passed (`/tmp/cvw-build-provenance-hooks.log`). The canonical master and public
candidate hashes remained unchanged. Context reported ready source, no issues,
and publication still requiring review. The site remained clean; no network
refresh, publication approval, sync, or push occurred.

### Medium — failed renders could overwrite completed documents — fixed

A real Pandoc Lua filter wrote incomplete content to the requested output and
then raised an error. Direct, single-request, and sequential rendering left those
bytes at the final destination, replacing a previous document or creating a
failed export. Six regressions reproduced the preservation failure; the existing
parallel path passed the same checks (`/tmp/cvw-render-recovery-red.log`). Two
additional regressions showed that duplicate and aliased destinations were
accepted (`/tmp/cvw-render-destinations-red.log`). The failed criteria were
preserving completed outputs on render failure and assigning one request per
destination.

`render_document` now delegates to the batch rendering owner. Both sequential and
parallel execution stage each output in an operation-owned temporary directory,
preserve its filename/extension, and promote completed files in request order.
Duplicate resolved targets are rejected before output-directory writes. Success
callbacks observe promoted files; callback errors and cancellation retain that
completed prefix and clean unpromoted staging after workers finish. The
[render recovery contract](../reference/configuration-contract.md#render-output-recovery)
distinguishes individual-output preservation from whole-build rollback and forced
process termination.

The focused suite passed 19 checks, including real Pandoc failures, destination
conflicts, callback errors and `KeyboardInterrupt`, and a real PDF signature
check (`/tmp/cvw-render-recovery-final-focused.log`). The concurrency test now
observes real renderer calls, and its failure test runs a real Lua filter instead
of substituting document output. The repository-relative CLI test was included
in the broader isolated-checkout run rather than rerun against live output paths.
All seven isolated CLI journey steps passed with empty stderr
(`/tmp/cvw-render-recovery-journey.json`).

The isolated full suite passed 884 tests with one opt-in remote skip and five
existing PyMuPDF/SWIG warnings (`/tmp/cvw-render-recovery-full.log`). Tested source
and test files matched the working tree byte-for-byte. The 13 documentation and
import-boundary checks passed. All pre-commit hooks, including the secret scan,
passed (`/tmp/cvw-render-recovery-hooks.log`). Canonical-master and public-candidate hashes stayed
unchanged; context reported a ready source, no issues, and publication still
requiring review. The site remained clean. No network refresh, publication
approval, site sync, or push occurred.

### Medium — some tests wrote to the current workspace — fixed

`tests/build/test_build.py`, `test_render.py`, and `test_render_formats.py` include
tests that unlinked/wrote `var/dist/base` using the current directory and default
configuration. Manifest, cover-letter, preview, and diff tests also depended on
ambient inputs or artifact roots. A regression launched four real tests from a
seeded operator workspace: the child tests passed but changed its existing files
and added artifacts (`/tmp/cvw-test-isolation-red.log`). The failed criterion was
that verification preserve the workspace from which it is launched.

`tests/conftest.py` now gives each test an empty temporary working directory.
Tests that need public sample inputs declare `sample_workspace`; custom inputs
remain in their existing temporary fixtures. Sample setup copies current public
data, variants, and themes, then uses the scaffold owner for neutral local
configuration. It does not copy operator inputs, artifacts, or publication settings.
Test setup restores the original working directory, and the temporary working
directory is separate from each test's `tmp_path` inventory.

The first full isolated run exposed 27 implicit fixture/path assumptions while
preserving every byte and directory entry beneath the checkout's protected input
and artifact roots (`/tmp/cvw-test-isolation-full.log` and
`/tmp/cvw-test-isolation-first-preservation.json`). Explicit fixture declarations
restore the intended positive and negative test boundaries. The preview-stop
hint test now verifies the command's complete argument list when launched outside
a checkout. Runtime application behavior and error assertions remain intact.

The harness pass uses the `autonomy-hardening` lane with `architecture-invariants`
and `knowledge-integrity` endpoints. Its deterministic-workspace criterion is zero
operator artifact changes while child tests pass; its documentation criterion is
one routed fixture contract with passing repository checks. The
[verification contract](../reference/verify-contract.md#test-workspaces) owns the
semantics, and `tests/AGENTS.md` routes maintainers to it. The acceptance regression
also verifies fresh empty directories across consecutive cases. Working-directory
isolation does not sandbox explicit filesystem paths.

Final verification passed 887 tests with one opt-in remote skip and five existing
PyMuPDF/SWIG warnings (`/tmp/cvw-test-isolation-final-full.log`). The same acceptance
checks passed in three independent pytest invocations: the 81-test focused run,
the full run, and the 16-test contract run (`/tmp/cvw-test-isolation-focused.log`
and `/tmp/cvw-test-isolation-contracts.log`). All child tests passed and each seeded
operator workspace retained its exact file hashes and directory inventory.

The normal `uv run pytest` invocation also preserved the real checkout's 8,382
protected entries under `local`, `var`, configuration, sample data, and themes:
no additions, removals, or mode/size/mtime/inode changes
(`/tmp/cvw-test-isolation-live-preservation.json`). Canonical-master and
public-candidate hashes were unchanged. Context remained ready with no issues
and publication requiring review; the site remained clean. No publication
approval, site sync, network refresh, or push occurred. The harness skill audit
passed (`/tmp/cvw-test-isolation-skill-audit.log`), as did all pre-commit hooks,
including the secret scan (`/tmp/cvw-test-isolation-hooks.log`).

During the render-recovery pass, fresh environment setup in its temporary checkout
could not complete offline: the locked PyMuPDF wheel was absent from the package cache
(`/tmp/cvw-render-recovery-checkout-sync.log`). Broader verification therefore
used existing installed dependencies with that temporary checkout's source
selected through `PYTHONPATH`; it did not prove a fresh offline installation.
The installed-wheel test retains its separate dependency-reuse contract.

### High — suggested project commands could mutate a different copy — fixed

Project command descriptions retained only the manifest ID after inspecting an
explicit directory. An isolated regression copied a registered project to an
archive, inspected it, and executed its suggested discard command: the command
deleted the configured same-ID neighbor's proposal instead of the inspected
copy. This violated the requirement that a described action preserve its target.

Selector resolution now distinguishes configured IDs from explicit paths.
Current-directory names cannot shadow IDs, missing explicit paths cannot become
store-relative selectors, and empty selectors cannot start a default build or
preview. Command descriptions require the selected directory; they retain the
ID only when the configured mapping selects that directory, otherwise quoting
its absolute path. CLI adapters translate selector errors before artifact writes.
Plain creation summaries consume the same configuration-preserving commands as
JSON. The [project selector contract](../reference/project-contract.md#project-selectors)
owns this behavior.

The inbox also inferred identity from a hard-coded `var/projects` path. It now
reads validated manifest identity for the registered proposal location and uses
the shared selector description, supporting custom stores and archived copies.
Invalid metadata remains visible through `project_error`, concrete registered
path commands, and no inferred preview action. Shared manifest reads reject
external symlinks and non-regular files before opening them. This is a local
ownership check, not protection against every concurrent filesystem replacement.

The routing regressions exercise real temporary projects, copied proposals,
custom configuration, generated commands, and unchanged neighboring artifacts.
The initial failures are recorded in `/tmp/cvw-project-routing-red.log`;
stronger invalid-selector checks failed in
`/tmp/cvw-project-routing-selector-red.log`. Inbox identity and bounded-manifest
read failures are in `/tmp/cvw-project-routing-inbox-red.log` and
`/tmp/cvw-project-routing-manifest-red.log`. No live proposal was discarded.

Run and review namespaces still use the manifest ID within a configuration.
Directory preservation does not make two copied manifests independent run
identities. A future clone/relocation workflow should define identity allocation,
registry updates, and retained-run references together rather than encourage
untracked directory copies. Configuration lifetime across side-effecting CLI
orchestration remains a separate audit item.

Verification: all 825 tests passed, with one opt-in remote skip and five existing
PyMuPDF/SWIG warnings (`/tmp/cvw-project-routing-full.log`). The 84 routing and
manifest checks passed, and all seven isolated CLI journey steps passed with
empty stderr (`/tmp/cvw-project-routing-manifest-green.log` and
`/tmp/cvw-project-routing-journey.json`). Ruff lint and formatting passed.
The canonical CV master and public candidate hashes remained unchanged; context
reported a ready source, no issues, and publication still requiring review.
The personal-site tree remained clean. This pass used no public network access,
publication approval, site sync, or push.

### Medium — retained project history depended on ephemeral proposal files — fixed

Detailed inspection required the executable-project loader. Discarded proposal
files, invalid YAML, or an unsupported patch format therefore hid retained job
context, guidance, and run history. Inspection also followed proposal symlinks
outside the project and attempted to open non-regular inputs.

`load_project_details` now separates validated recorded information from
proposal availability. It reports typed per-input issues (`missing`, `unreadable`,
or `invalid`), checks project ownership and regular-file kind before proposal
reads, and represents unavailable fields as unknown rather than empty. Full
inspection preserves retained observations and omits commands requiring live
proposals. CLI and preview share the warning; the
[inspection contract](../reference/project-inspection.md) owns these semantics.
Build/apply retain their executable-input prerequisites.

Review bundle creation had the same coupling through its shared import target
resolver. `resolve_review_run` now selects only the retained run and destination;
`resolve_review_target` adds current source/proposal inputs for import. Packaging
can therefore copy and record immutable run artifacts after proposal expiration,
while import still requires the inputs needed to interpret edits. Run-only
packaging retains the project review namespace even if current project inputs
are missing.

Fifteen initial tests reproduced unavailable-history, proposal-read boundary,
and retained-review failures (`/tmp/cvw-project-history-red.log`). Additional
real-build cases package both explicit-project and run-only selections after
removing live proposals, configured variant, and source location. They validate
the bundle's source record and copied bytes; build/apply rejection and inspection
read-only behavior are also checked. No historical proposals were migrated.

Live read-only inspection now succeeds for all 25 projects: 18 have available
proposal inputs, and seven report an invalid patch format while retaining their
history. Evidence: `/tmp/cvw-project-history-live.json`. Local browser component
verification rendered actual inspector output for a missing proposal patch:
the warning was absent before the presentation fix and visible afterward, with
no horizontal overflow or console errors. The browser check deliberately supplied
the captured inspection payload to the existing preview component; it does not
claim that a failed build refreshes the controller's last-successful observations.
Evidence is under `var/runs/preview/history-inspection-audit/`, with fixture
location in `/tmp/cvw-project-history-preview.json`. The tab and server were closed.

### Medium — import target resolution lost project identity — fixed for missing and mismatched projects

Run-only import swallowed project-loading errors and continued through configured
variant resolution. It also accepted a current project whose manifest identity
no longer matched the project named by the source run. This conflated retained
run review with the mutable inputs needed for guarded patch construction.

Project-scoped import now preserves loading failures and rejects mismatched
project identity before conversion or draft writes. Two real-build
tests reproduced the unrelated variant-resolution path, and one test reproduced
acceptance of the mismatched identity. Their failing evidence is in
`/tmp/cvw-project-history-import-red.log` and
`/tmp/cvw-project-history-identity-red.log`. The
[review contract](../reference/review-contract.md) defines the packaging/import
boundary. Input files still have separate lifetimes; these checks do not prove
one immutable source/variant/patch bundle or protect against every concurrent edit.

Verification for the retained-history and import-boundary changes: the final
inclusive suite passed 800 tests with one opt-in remote skip and five existing
PyMuPDF/SWIG warnings. The 125 focused checks and seven-step isolated journey
also passed; journey stderr was empty. Evidence:
`/tmp/cvw-project-history-final-full.log`,
`/tmp/cvw-project-history-final-focused.log`, and
`/tmp/cvw-project-history-journey.json`. Canonical master and public candidate
hashes remained unchanged, and the personal-site tree remained clean. This pass
did not modify historical proposals, approve publication, sync the site, or push.

### Medium — project inspection mixed settings and duplicated adapter decisions — fixed

CLI show and preview separately loaded project details, optional plans, artifact
observations, and guidance comparisons. Full inspection also reopened workbench
settings for selector resolution, run lookup, command suggestions, and provenance.
An intervening configuration edit hid an existing run and falsely reported a
changed default variant in the same response; removal caused inspection to fail.

`workspace/projects/` now separates inventory, inspection composition, command
descriptions, and guidance presentation. Full and preview APIs share the detail
and observation reads while retaining their different payloads and error
boundaries. Full inspection passes one captured configuration through all of
its decision owners. CLI errors now explain missing files, invalid UTF-8,
malformed YAML, and non-mapping settings without a traceback or partial JSON.
The [inspection contract](../reference/project-inspection.md) owns these semantics;
scoped instructions and boundary tests keep implementation out of the package
entrypoint and adapters out of workspace code.

The extraction baseline and focused suite each passed 109 tests. Before/after
capture preserved 32 outputs across eight project states: healthy, absent plan,
invalid plan, changed job file, retargeted proposal, unknown provenance, invalid
metadata, and absent proposal inputs. Snapshot tests initially failed five cases
for edited/removed settings and explicit captured settings. Four additional CLI
tests reproduced missing error diagnostics. After fixes, all 15 focused API and
boundary checks passed, including read-only and terminal-independent inspection.
Evidence: `/tmp/cvw-shared-project-inspection-before.json`,
`/tmp/cvw-shared-project-inspection-after.json`,
`/tmp/cvw-project-inspection-config-red.log`,
`/tmp/cvw-project-inspection-errors-red.log`, and
`/tmp/cvw-project-inspection-final-focused.log`.

The inclusive suite passed 782 tests, with one opt-in remote skip and the five
existing PyMuPDF/SWIG warnings. The seven-step isolated document journey passed
with empty stderr, and the final 32-output capture remained byte-identical to
the baseline. Evidence: `/tmp/cvw-shared-project-inspection-full.log`,
`/tmp/cvw-shared-project-inspection-journey.json`, and
`/tmp/cvw-shared-project-inspection-final.json`. The canonical master and public
candidate hashes remained unchanged; live context was source-ready with zero
issues and publication `review_required`. The personal-site tree stayed clean.

The configuration guarantee is not a transaction across project, source,
variant, and run files. Preview retains partial diagnostics when inputs are
unavailable. Detailed inspection still requires executable proposal artifacts;
historical/partial project inspection remains a separate improvement.

### Medium — saved guidance was not bound to its consumed inputs — fixed for declared guidance inputs

Job-file checks compared bytes only with the current project manifest. Updating
both a file and its manifest hash could make those checks match while the saved
recommendation still described earlier input. Source tag counts, ranking catalog
fields, and the default variant had no saved comparison record at all.

New guidance records versioned fingerprints for all five consumed input groups.
Job parsing and hashes use the same captured bytes; source/catalog fingerprints
use the values already loaded for scoring. Ranking and fingerprinting share one
catalog projection. `inspect_guidance_inputs` reports matching inputs, changes,
or unverifiable comparisons and preserves known changes when another input is
unavailable. CLI and preview share its presentation. Preview honors the selected
source override and labels cached observations by their last successful build.
The [provenance contract](../reference/guidance-provenance.md) owns the schema,
algorithm-version rule, exact comparison scope, and input-lifetime limits.

Evidence: `/tmp/cvw-guidance-provenance-red.log` (11 initial failures),
`/tmp/cvw-guidance-provenance-ui-red.log` (three missing adapter cases), and
`/tmp/cvw-guidance-provenance-focused-green.log` (103 passing checks).
Tests cover changed files plus updated manifest hashes, inputs edited after
capture, unsupported/malformed records, unavailable inputs, explicit config
snapshots, and real preview builds with a source override. Prose/render changes
outside ranking inputs remain matches. A legacy preview fixture now explicitly
expects unknown provenance; historical records are not silently upgraded.

The full suite passed 771 tests, with one opt-in remote skip and five existing
PyMuPDF/SWIG warnings. The seven-step isolated document journey passed. Local
Chrome DevTools verification showed matching job files alongside changed source
tag inputs, no horizontal overflow, and no console warnings/errors. Restoring
the source triggered a rebuild that cleared the warning and reported a match.
Evidence: `/tmp/cvw-guidance-provenance-full.log`,
`/tmp/cvw-guidance-provenance-journey.json`, and the isolated browser bundle
located by `/tmp/cvw-guidance-provenance-preview-fixture.json`.
Ruff, formatting, and pre-commit checks passed. The audit tab and preview server
were closed. Final context remained source-ready with no issues and publication
`review_required`; the master/candidate hashes and personal-site tree were
unchanged. No approval, site sync, or push occurred.

Live read-only inspection found 11 plans without verifiable provenance, seven
projects without plans, and seven whose existing proposal format prevented
detailed inspection. No historical plan was rewritten. Provenance is not
authenticated, a complete source-document fingerprint, or publication approval;
inspection does not refetch the original job source. Inputs still have separate
read lifetimes rather than one locked filesystem snapshot.

### Medium — inspection did not report changed or missing stored job context — fixed for recorded artifact observations

Project creation recorded extracted-text and signals digests, but inspection
never compared those records with the current files. Saved guidance could
remain visible without any warning after a stored job artifact changed,
disappeared, or became unreadable. Matching selected variant IDs did not catch
this condition. This was a gap in observable state rather than a reason to
conflate inventory, guidance, and immutable-run review readiness.

`ops.projects.artifacts` now owns streaming comparisons of the two recorded
job artifacts. Its public `inspect_project_artifacts` API works without retained
proposals. `load_project_details` includes the same observations using its
already parsed manifest. Each observation reports `matches_record`, `changed`,
`missing`, or `unreadable`, with recorded/observed digests and safe read errors.
It rechecks path ownership and rejects nonregular files before opening them.
CLI and preview share status/warning presentation through the workspace owner.
The preview labels observations as belonging to the last build and caches them
for status polling. Rebuild refreshes them; job-file changes alone are not watched.

The recommendation text also now asks operators to review missing job signals
and add only supported experience, rather than prescribing that every missing
signal be patched into the source facts.

Evidence: `/tmp/cvw-project-artifact-checks-red.log` (11 missing API/state cases),
`/tmp/cvw-project-freshness-presentation-red.log` (seven missing presentation
cases), and `/tmp/cvw-project-freshness-focused-green.log` (126 passing checks).
Adversarial checks cover directories, a named pipe, denied reads, and a path
replaced with an outside symlink after metadata capture. The latter performs
no outside read; inspection uses one manifest read for detailed state.

Final verification: 741 tests passed, one opt-in remote test skipped, and the
five existing PyMuPDF/SWIG warnings remained. The seven-step isolated journey
and a separate real project build to Markdown/PDF/DOCX passed. Inspection of
that build independently reported changed job context and available run review
inputs. Live inspection found all 50 recorded job files across 25 projects
matched their current records, including projects with legacy proposal formats.
Evidence: `/tmp/cvw-project-freshness-full.log`,
`/tmp/cvw-project-freshness-journey.json`,
`/tmp/cvw-project-freshness-built-show.json`, and
`/tmp/cvw-project-freshness-observations.json`.

Local Chrome DevTools inspection confirmed the warning and supported-experience
guidance as rendered text, with no horizontal overflow or console warnings/errors.
The fixture/evidence location is recorded in
`/tmp/cvw-project-freshness-preview-fixture.json`. Snapshot, screenshot, and
console evidence remain in its isolated `var/runs/preview/freshness-audit/`.
Restoring the fixture's original job bytes and clicking Rebuild changed the
status to match and cleared the warning; `restored.snapshot.md` records that
state. The audit tab and server were closed. Ruff, formatting, and pre-commit
checks passed. Final context remained ready with no issues and publication
`review_required`; the master, candidate PDF, and personal site were unchanged.
No publication approval, site sync, or push occurred.

These checks compare bytes with the current manifest. They do not authenticate
the record, bind a saved plan to immutable input hashes, validate the optional raw
capture, prove freshness of external job/source/catalog data, or isolate reads
from subsequent filesystem changes. Those remain explicit provenance/lifetime
follow-ups; matching files are not publication approval.

### High for local confidentiality — project guidance followed paths outside its owner — fixed for stable paths

Detailed inspection accepted absolute/traversing artifact locators and symlinks
outside the project. Real CLI fixtures read an unrelated `proposal-plan.json`
through all three routes. A second fixture showed that valid signals metadata
still allowed an outside plan through a symlink on the plan file itself, in
both CLI inspection and preview context.

The manifest owner now resolves stored job artifact locators within the owning
project. `ops.projects.load_project_plan` additionally checks the derived plan
file before reading it; CLI and preview share this operation. Original source
provenance and explicitly selected SoT paths remain separate external inputs.
Outside plan contents are not read or echoed, and optional-plan failures retain
other inspection data. Internal absolute references and symlinks still work.
Resolution checks do not isolate later reads from concurrent filesystem edits.

Evidence: `/tmp/cvw-project-artifact-path-red.log` (three external reads),
`/tmp/cvw-project-plan-symlink-red.log` (both consumers read the outside plan),
and `/tmp/cvw-project-plan-symlink-green.log` (focused regression and compatibility
checks). Fixtures and checks use local files; no external destination was contacted.

### Medium — project metadata coercion hid errors and broke inventory JSON — fixed

Detailed inspection stringified malformed timestamps, source values, and hashes,
ignored the extracted-text digest, and accepted false-valued raw-path metadata
as absence. Inventory emitted arbitrary YAML values, including a set that
prevented context JSON serialization. Compact CLI projection also dropped the
new diagnostic count after workspace inspection supplied it.

Typed metadata now belongs to `ops/projects/manifest.py` and `records.py`.
Detailed reads validate timestamps, source type/value, digest shape, and artifact
locators. Inventory uses `ProjectSummary`: identity remains visible while
malformed displayed fields become unknown with field-specific diagnostics.
Both full and compact context expose the error count; compact CLI output keeps
the project section supplied by its inventory owner. This partial summary does
not require executable proposals or establish build/review readiness. Recorded
hash syntax is validated separately from current file presence and byte freshness.

Evidence: `/tmp/cvw-project-metadata-red.log` (27 failing cases),
`/tmp/cvw-project-metadata-focused-final.log` (compact projection failures), and
`/tmp/cvw-project-metadata-focused-green.log` (129 passing checks, including both
strict modes). Older detailed-inspection fixtures now record actual local-file
digests instead of short placeholder strings.

Final metadata/ownership verification: 721 tests passed, one opt-in remote test
skipped, and the five existing PyMuPDF/SWIG warnings remained. The seven-step
isolated document journey passed, with no stderr from the journey driver.
Ruff, formatting, and all-file pre-commit checks passed. Evidence:
`/tmp/cvw-project-metadata-full.log`, `/tmp/cvw-project-metadata-journey.json`,
and `/tmp/cvw-project-metadata-hooks.log`. No presentation assets changed in
this pass; preview-context regression tests covered its read behavior.

Live read-only inspection found 25 identifiable projects with no displayed
metadata errors. Eighteen passed detailed inspection; seven reached the existing
unsupported patch-format error in the unchanged patch loader. Retain these as
a migration/disposition follow-up, rather than interpreting inventory visibility
as executable readiness. Source data was ready, publication remained
`review_required`, and master/candidate hashes plus the personal-site tree were
unchanged. No publication approval, site sync, or push occurred.

### High for local edit preservation — retargeting overwrote intervening edits — fixed for observed changes

Retargeting loaded validated manifest metadata, then reread the raw document for
serialization. A fixture replaced the manifest after the first read with an
invalid project identity: retargeting wrote from that unvalidated generation
before its final load failed. A separate fixture edited the proposal after it
was read; retargeting silently overwrote the edit. These violate the requirement
to validate the inputs used for mutation and preserve observed intervening edits.

The manifest owner now returns original bytes and the parsed document from one
read. Retargeting derives its metadata and output from that validated document,
captures the proposal bytes used for its ID, and returns the spec it wrote.
The existing recoverable-write helper accepts expected destination bytes and
checks them before staging and before replacement. Mismatches abort without
replacing files. Tests also cover edits during backup staging, absent versus
empty destinations, dangling symlinks, malformed expectations, and safe errors
for invalid proposal/base-variant inputs. Existing rollback coverage remains.

Evidence: `/tmp/cvw-retarget-intervening-edit-red.log`,
`/tmp/cvw-atomic-expected-red.log`, `/tmp/cvw-retarget-input-errors-red.log`, and
`/tmp/cvw-retarget-guards-green.log` (100 focused checks passed). Byte checks do
not serialize other writers or guarantee a multi-file transaction. Edits after
the final check, process termination, cancellation, and global source freshness
remain outside this contract.

### Medium — saved guidance hid selection changes and could break inspection — fixed

Retargeting left the original recommendation plan in place, but neither project
inspection nor preview explained that its recorded applied variant differed
from the current manifest. Invalid UTF-8 or an unreadable optional plan also
aborted those read paths instead of preserving the available project details.

Both consumers now share optional JSON loading and selection-warning semantics
through `workspace.project_guidance`. Changed or unverifiable recorded selections
produce `proposal_plan_warning`; read/encoding/JSON errors produce
`proposal_plan_error`. The CLI and preview show these diagnostics. Retargeting
does not rewrite historical guidance to imply a fresh recommendation. Matching
variant IDs do not prove freshness of source facts, job content, or catalog data.

Six RED cases and one positive control exercised the real guide, retarget,
inspection, and preview-context paths. Evidence:
`/tmp/cvw-guidance-selection-red.log` and
`/tmp/cvw-guidance-selection-green.log` (80 checks passed). A local Chrome
DevTools inspection confirmed the warning as rendered text, no horizontal
overflow, and no console warnings/errors. Snapshot, screenshot, and console
evidence live under the isolated fixture's `var/runs/preview/retarget-audit/`;
`/tmp/cvw-retarget-preview-fixture.json` records its location. The preview tab
and server were closed after inspection.

Final retarget/guidance verification: 686 tests passed, with one opt-in remote
skip and the five existing PyMuPDF/SWIG warnings. An older preview fixture
without an applied variant now expects the explicit unknown-selection warning;
its focused check and the repeated full suite passed. The seven-step isolated
journey passed with empty stderr at each step. Ruff, formatting, and pre-commit
checks passed. Evidence: `/tmp/cvw-retarget-full-final.log`,
`/tmp/cvw-retarget-preview-compatibility.log`, `/tmp/cvw-retarget-journey.json`,
and `/tmp/cvw-retarget-hooks.log`. Live context reported ready source data,
no issues, and `review_required` publication. Master/candidate hashes and the
personal site were unchanged; no publication approval, sync, or push occurred.

### Medium — direct creation validated inputs after artifact writes — fixed

Nine local fixtures demonstrated late validation or acceptance of invalid job
text/kind, project identity, base variant, lifetime, cleanup root, registry
contents, or source kind. Creation accepted a regular file as its SoT
directory and copied a variant whose output filename violated the normal
variant schema. A URL fixture reached the fetch boundary before noticing a
missing base variant. These violate the operation's preflight-before-write
contract; successful cleanup did not make the late validation acceptable.

Creation now preflights local inputs through their existing owners: project IDs
in `identity.py`, parsed variants in `variants.py`, and prospective registration
in `variant_lifecycle.py`. The variant parser is shared with normal file
loading, and registration rechecks current eligibility under its write lock.
The selected variant and local job text are captured before staging and reused
for the output; extension metadata remains intact. An omitted slug still derives
an ID, while empty or incorrectly typed explicit values are rejected. Malformed
variant YAML errors identify the file without echoing its contents.

Ten initial RED cases proved the late writes/acceptance/fetch failures. Five
additional RED cases proved silent slug fallback and diagnostic content echo.
A real-input replacement check confirms that changing the job and variant after
staging begins does not substitute unvalidated content. The 94 focused checks
passed. Evidence: `/tmp/cvw-creation-preflight-red.log`,
`/tmp/cvw-creation-input-contract-red.log`, and
`/tmp/cvw-creation-input-contract-green.log`.

The real `project new` CLI rejected an unsafe variant with exit 1 and an
unchanged fixture tree, then succeeded with exit 0, valid JSON, and empty stderr
after the fixture was corrected. Evidence: `/tmp/cvw-creation-cli-evidence.json`.
Direct creation requires a source directory; full source-content validation
remains in guidance/build. Independent file captures and preliminary registry
checks provide no global snapshot, reservation, or concurrent-write isolation.

Final preflight verification: 666 tests passed, one opt-in integration test was
skipped, and the five existing dependency warnings remained. All seven isolated
build/preview/review journey steps passed with empty stderr. Ruff, formatting,
and pre-commit checks including secret scanning passed. Evidence:
`/tmp/cvw-creation-preflight-full.log`,
`/tmp/cvw-creation-preflight-journey.json`, and
`/tmp/cvw-creation-preflight-hooks.log`.

### High for local artifact integrity — creation cleanup deleted another directory — fixed

Creation previously removed both staging and final paths after any failure,
without establishing ownership of the final directory. A real rename collision
deleted a competing destination and its sentinel file. A second fixture replaced
the published directory during registration; cleanup also deleted that
replacement. Both failures violate the project operation's artifact-ownership
boundary.

File and URL creation now share one lifecycle context. Cleanup follows the
successful rename state and checks the original directory identity before
deletion. An observed replacement remains intact; deletion failures retain both
the creation and cleanup diagnostics. Tests use real local scaffold, filesystem,
and registry operations with narrowly injected failures. The implementation
does not establish exclusive creation or eliminate filesystem races. See the
[mutation contract](../reference/project-contract.md#mutation-recovery).

Evidence: `/tmp/cvw-project-creation-ownership-red.log`,
`/tmp/cvw-project-creation-replacement-red.log`,
`/tmp/cvw-project-creation-replacement-green.log`, and
`/tmp/cvw-project-creation-cleanup-green.log`.

### Medium — retargeting could leave proposal and manifest inconsistent — fixed for I/O recovery

The two direct writes could leave the proposal changed after the manifest save
failed. A real project fixture with an injected second-save failure reproduced
the mismatch. Retargeting now uses the existing recoverable file-replacement
owner, restoring the prior files after an ordinary replacement failure. It
preserves the public proposal ID and reports recovery errors through
`ProjectError`. Shared-helper tests cover incomplete rollback and retained
backups. Independent input reads, process termination, cancellation, and
concurrent visibility remain outside this guarantee.

Evidence: `/tmp/cvw-project-retarget-recovery-red.log` and
`/tmp/cvw-project-mutation-recovery-green.log` (38 passing focused tests).

Mutation-recovery verification: 649 tests passed, one opt-in integration test
was skipped, and the five existing PyMuPDF/SWIG warnings remained. The isolated
seven-step build/preview/review journey passed with empty stderr at each step.
Ruff, formatting, and pre-commit checks including secret scanning passed.
Evidence is `/tmp/cvw-project-mutation-full.log`,
`/tmp/cvw-project-mutation-journey.json`, and
`/tmp/cvw-project-mutation-hooks.log`. Live source status was ready without
context issues; publication remained `review_required`. The canonical master
and candidate PDF hashes were unchanged, and the personal site stayed clean.
No site sync, publication approval, or push was performed.

### Medium — guidance lived in the CLI and missed cleanup after failures — fixed

The guide adapter coordinated source loading, creation, ranking, retargeting,
and proposal-plan writes. Invalid catalog entries were loaded after creation;
a real local fixture failed with a project and proposal already present.
`ops.projects.guide_project` now owns the workflow and returns a structured
result without terminal output or preview launch. The CLI adapter presents that
result and retains its public command surface.

Catalog, selected-variant, and local job-file preflight occurs before project
creation. Empty/false-valued explicit variants no longer select the default;
blank URLs and multiple supplied job sources are rejected. Source errors retain
individual diagnostics in `ProjectGuideError.errors`, including invalid
URL-registry settings. Guidance/retarget/plan failures discard the partial
project and active proposal, retaining both diagnostics if cleanup fails.
Cancellation cleans up and preserves the interrupt. Registry history may retain
a discarded entry; this is recovery, not a multi-file transaction.

One configuration snapshot now reaches source/default selection, creation,
retargeting, registration, and cleanup. Real edits/removals of the workbench file
between reads previously changed destinations or aborted the workflow; supplied
snapshots were also reduced back to a mutable path. Those cases now retain the
captured settings. Plan-write failure tests remove the config before cleanup,
verifying that recovery uses the captured generation too.

Source facts, job files, variant definitions, project manifests, and proposal
files retain independent read lifetimes across the complete guide workflow.
The subsequent creation-preflight and mutation-recovery passes address late
validation and ordinary creation/retarget write failures; concurrent isolation
remains a distinct mutation-contract follow-up.

Four real stable-input comparisons (recommended/explicit selection in JSON/plain
mode) match the previous guide adapter byte-for-byte. All 65 help screens, seven
workspace snapshots, and 107 other CLI function bodies remain unchanged. New
API tests cover normal results, individual source errors, configuration drift,
invalid selection, temporary-directory writes, real plan-write failure, and
cancellation. Evidence is under `/tmp/cvw-guide-api-*`, with individual red/green
logs under `/tmp/cvw-guide-*`.

Final verification for guided creation: 131 focused tests and 645 tests in
default discovery passed, with one opt-in remote skip and the five existing
PyMuPDF/SWIG deprecation warnings. The isolated seven-step journey passed with
empty stderr at every step. Ruff, formatting, and all pre-commit hooks including
secret scanning passed. Commands were `UV_OFFLINE=1 uv run pytest`,
`UV_OFFLINE=1 uv run python scripts/verify_repo.py --json`, and
`UV_OFFLINE=1 uv run pre-commit run --all-files`. Live context remained ready
without issues and with `review_required` publication. Master/candidate hashes
were unchanged; the site remained clean on `main`, with no sync or push.

### High for local artifact integrity — project identity escaped run destinations — fixed

Real isolated project builds accepted both `../../outside-runs` and an absolute
temporary path as a manifest's project ID, then wrote source copies and build
outputs outside the intended project-run directory. The loader only coerced the
field with `str(...).strip()`. Null, boolean, numeric, collection, and path-like
identifiers also passed through project and inventory readers inconsistently.

`ops.projects.load_project_metadata` now owns manifest reading and identity
validation for both executable projects and workspace inventory. IDs and base
variant selectors must be nonempty strings with the documented identifier
alphabet. Malformed UTF-8/YAML and read failures become `ProjectError`; context
lists the affected project as invalid, and explicit commands fail without
printing parser snippets. A retained project's identity does not require its
proposal files, so pruning proposals does not erase the inventory entry.

Detailed project inspection also combined identity from one manifest read with
description from another. A real file replacement between reads reproduced the
mixed generation. It now derives both from one parsed manifest; a subsequent
inspection reads the current file. This is a read contract, not transactional
retargeting or a complete typed schema for job, source, signal, and proposal
metadata. Those remain explicit project-domain follow-ups.

Adversarial tests first reproduced 20 identity failures, three unhandled read
errors, and one mixed-generation failure. The identity cases included two real
builds escaping into temporary destinations. Successful rejection now leaves the
entire fixture tree unchanged. Retained-project inventory and a real file edit
between reads exercise the corresponding positive and freshness contracts.

Verification for project manifest ownership: 113 focused tests passed, followed
by 624 tests in default discovery, one opt-in remote skip, and the five existing
PyMuPDF/SWIG warnings. The seven-step isolated journey passed with empty stderr
for every step. Commands were `UV_OFFLINE=1 uv run pytest` and
`UV_OFFLINE=1 uv run python scripts/verify_repo.py --json`; logs are
`/tmp/cvw-project-manifest-full.log` and
`/tmp/cvw-project-manifest-journey.json`. Live context retained ready source data,
no issues, and `review_required` publication. Master and candidate hashes were
unchanged, and the site tree remained clean on `main`.

### High for local artifact integrity — variant names escaped output destinations — fixed

In an isolated real build, `output_name: ../outside-variant` wrote Markdown to
the parent of the selected variant output directory. The manifest retained only
the basename and therefore pointed to a missing artifact within that directory.
Variant IDs also entered build and promotion paths without identifier validation.
This is a local input/write boundary; no remote exploit was attempted.

`variants.py` now owns identity and filename-stem validation, including direct
model construction. Config path resolution reuses the identifier validator, and
output path construction rejects path-bearing extensions. Standard build/render
commands reject these inputs before creating files or directories. Human-readable
output stems remain supported. The initial regression run had 30 intended
failures, including real escaped build/render outputs; name validation and
promotion checks now protect the same boundary across callers.

Evidence: `/tmp/cvw-variant-output-boundary-evidence.json` and
`/tmp/cvw-artifact-names-red.log`.

### High — default test discovery omitted the build domain — fixed

The installed pytest default `norecursedirs` includes `build`. With no explicit
override, `uv run pytest` silently omitted all 13 test-bearing files beneath
`tests/build/`. Before this fix, default-suite counts in this audit describe
only what pytest collected; the separately reported targeted build checks and
installed-wheel journey remain distinct evidence.

The repository now declares recursion exclusions explicitly and verifies that
every test-bearing Python file appears in real default collection. The failing
regression listed all 13 omitted files before the configuration change.
This closes a false-green gate; discovery alone is not proof the newly included
tests pass. Full execution and a repeatable collection check are required.

Harness lane: `autonomy-hardening`, targeting deterministic verification (L2).
The `architecture-invariants` endpoint requires zero omitted test-bearing files;
the `knowledge-integrity` endpoint requires accurate verification scope in the
owning contract and this audit. Failure lists identify the files to restore to
collection. The source for the dependency behavior was the installed
`_pytest/main.py` default configuration, verified locally.

### High — publication policy could be bypassed through the Python API — fixed

[syncing.py](../../src/cvworkbench/ops/syncing.py) accepted a missing policy
argument as permission to skip disclosure validation. A direct API test copied
a PDF containing a forbidden phone number. The API now resolves the configured
policy by default and rejects a missing policy before any site write. Actual
PDF graphics are also checked against the approved fingerprint, not merely the
manifest's declaration.

Failed criterion: the [site contract](../reference/site-contract.md) requires
source, policy, and artifact validation before every write. Negative-path tests
cover policy omission, missing policy, and unapproved graphics.

### High — sync could copy unreviewed bytes under an approved hash — fixed

A deterministic filesystem interleaving replaced the source PDF after sync
planning. `_apply_plan` reopened that path, copied a PDF containing a forbidden
test contact, and wrote the earlier approved hash to the site manifest. Another
test showed signature and hash validation accepting different reads of one
changing source. A third used real preparation/review operations to demonstrate
sync accepting a review for a different publication generation.

`artifact.py` now captures one immutable PDF payload and validates its identity;
the PDF disclosure validator accepts that payload directly. Sync compares its
hash with the current reviewed publication and carries its bytes through the
copy plan and atomic replacement. Negative tests prove generation mismatch
causes no site writes, and source replacement after planning cannot change
copied content. These tests use temporary sites and authored sources only.

Failed criterion: the [site contract](../reference/site-contract.md) requires
the published bytes, manifest hash, disclosure checks, and review to agree.
Configuration reads remain a separate operation-snapshot improvement; this
change does not claim a filesystem-wide transaction or lock.

### Medium — authored provenance accepted malformed values — fixed

The manifest validator accepted boolean/floating schema versions, negative
redaction counts, malformed source hashes, path-valued source names, impossible
coverage values, undeclared fields, and duplicate JSON keys. These weaknesses
made a successful eligibility check weaker than the declared authored-source
contract. They do not by themselves prove a public disclosure bypass.

`ops/publication/manifest.py` owns a strict schema used by both preparation and
artifact validation. Existing generated manifest structure is retained; no
missing-field defaults or coercion repair malformed provenance. Adversarial
tests exercise the previously accepted cases using real prepared artifacts.

### High — local preview accepted foreign browser requests — fixed

[preview.py](../../src/cvworkbench/dev/preview.py) accepted foreign Host/Origin
headers and prefix-matched action routes. Real local HTTP requests could read
state, rebuild, or stop the server without satisfying a same-origin contract.
Malformed lengths, oversized bodies, invalid UTF-8, and truncated valid JSON
also lacked a consistent rejection boundary.

[preview_http.py](../../src/cvworkbench/dev/preview_http.py) now owns origin and
body-size rules. Tests exercise the actual server with sample content, check
that rejected requests do not rebuild/stop it, and retain the normal local
render path. This protects the browser-to-preview boundary; it is not an
authentication boundary against other processes running as the same OS user.

### High — rollback cleanup could destroy the recovery copy — fixed

[storage.py](../../src/cvworkbench/storage.py) deleted backups even when
restoring them failed. It also left temporary files after failed backup staging.
Injected filesystem failures now prove that incomplete rollback retains the
original recovery bytes and reports their path, while staging failures leave
the prior destination untouched.

### High for standalone distribution — installed package lacks resources — fixed

An offline wheel build succeeded, but the wheel contained zero themes, filters,
or sample templates. Loading that wheel outside the checkout produced a missing
filter path and `ScaffoldError: Template directory not found` during init.

Evidence: [build/paths.py](../../src/cvworkbench/build/paths.py) and
[ops/scaffold.py](../../src/cvworkbench/ops/scaffold.py) resolve resources through
source-file ancestry; [pyproject.toml](../../pyproject.toml) packages Python code
without the required root resource trees. The
[verification harness](../reference/verify-contract.md) tests checkout-backed
journeys, so it does not detect this failure.

Implemented follow-up: explicit wheel mappings expose the existing canonical
resources through `cvworkbench_data`, resolved by `resources.py` with
`importlib.resources`. Editable and wheel installations use the same data
contract. Workspace copies remain editable; source resources are not inferred
from repository ancestry. Neutral publication/destination templates avoid
inheriting this checkout's approved CV fingerprint or personal-site path.

The installed-wheel regression builds and installs the distribution, excludes
checkout imports, then runs init, doctor, context, resume and cover-letter
exports, and one-shot preview. It reuses locked runtime dependencies locally;
it does not claim to re-test package-index resolution. The targeted suite passed
15 tests. Initialization also preserves existing source/theme settings and
rejects missing template inputs before creating a partial workspace. Installed
command suggestions now use `cvw` directly. See the
[distribution contract](../reference/verify-contract.md#installed-distribution).

### Medium — publication is absent from the bootstrap workflow model — fixed

The live `context` recipe index includes generated build, preview, import, and
tailoring flows, but no authored-publication journey or publication freshness
state. It cannot identify the canonical editable source from the sanitized
provenance manifest, which intentionally omits private paths. Operators must
reconstruct the source/export pair.

Preparation now produces a hash-addressed local visual packet from the exact
sanitized PDF. [review catalog](../../src/cvworkbench/ops/review/catalog.py)
discovers actual content and publication packets, including nested project
reviews; container directories no longer masquerade as review items.

Implemented follow-up: [the publication lifecycle](../reference/publication-contract.md)
defines a private preparation snapshot, source/export/configuration freshness,
packet integrity, and a review receipt bound to the exact PDF and preparation.
`context`, `status`, and `publication status` expose the observed phase;
`authored.publish` provides a source-aware recipe with a manual review step.
Publication defaults follow the declared site variant independently of generated
build defaults. Sync rejects stale, missing and unreviewed inputs before writing.
Private records use owner-only permissions and never enter the site manifest.

The static packet describes itself as evidence and directs the operator to live
status, avoiding a permanently stale "review required" label. Local `reviewed`
means ready for sync's destination checks; it intentionally does not claim that
a remote deployment or even the configured site checkout has been updated.
Destination/deployment observability remains a distinct future inspection surface.

### Medium — formatting fidelity is not document usability — partly fixed

The supplied screenshot matched the prepared PDF exactly. The Word source had
right-aligned header paragraphs and a large manual name indent. Phone redaction
preserved surviving glyph coordinates and consequently left an alignment gap.
A review copy now aligns all three header paragraphs with the body and uses
concise profile labels. Body wording and page assignment remain unchanged across
all three public pages.

Visual review also exposed lost hyperlink annotations: a phone redaction touched
the edge of the next line's clickable rectangles. A regression test reproduces
this without private data. Valid rectangles are now tightened to their labels;
the prepared candidate retains all three approved profile destinations.

The authored DOCX has 121 paragraphs: 90 direct/default and 31 `ListParagraph`.
The public PDF has no outline entries or structure tree. Proposed next work:
semantic Word styles for the name, contacts, headings, body, and date alignment,
followed by a local tagged-PDF export contract. Verify reading order, heading
navigation, link semantics, and redaction of both visible and structural text.
The existing token-frequency correspondence threshold is a plausibility check,
not proof of identical wording, order, or fresh export; surface that distinction
and add section/order comparison evidence before strengthening its claim.

The terminal section redaction also leaves the References heading's underline
because the current fidelity contract preserves all approved graphics. Resolve
that ornament in the authored style or through an explicit, narrowly scoped
decoration-redaction contract; do not hide it with a website-layer patch.

### Medium — transport, workflow decisions, and presentation share large files — partly fixed

At audit baseline, [cli/app.py](../../src/cvworkbench/cli/app.py) contained about
7,200 lines, 51 registered command functions, and a 563-line recipe builder.
[dev/preview.py](../../src/cvworkbench/dev/preview.py) embedded a 1,281-line
HTML/CSS/JavaScript page alongside its controller and HTTP server.

Implemented follow-up: the preview page now has separate markup, stylesheet,
and interaction assets under `dev/assets/preview/`, assembled by the small
`dev/presentation.py` module. `preview.py` is 866 lines. The assembled response
matches the previous page except outer whitespace normalized by repository
hooks, and still uses one request for markup/styles/script. Focused tests cover
the UI contracts, real HTTP boundary, controller behavior, and installed-wheel
asset availability. Publication command adapters now live in
`cli/commands/publication.py`; lifecycle code is grouped under `ops/publication/` with
scoped owner guidance. Publication inspection and workflow description have a
workspace module shared by context and status.

Workspace inspection now lives in `workspace/context.py`, backed by separate
source, variant, run, project, review, publication, and project-guidance owners.
`cli/app.py` is a 382-line registration surface after command-family extraction.
The recipe catalog selects and orders descriptions from setup, build, review,
project, and maintenance modules. No recipe body spans the whole product flow.
The inspection API raises domain exceptions without terminal output; the CLI
retains its prior messages and exit codes. Seven deterministic before/after CLI
snapshots match byte-for-byte, including strict failure and explicit source
selection. Import-direction tests protect workspace/adapter and domain owners.

Command ownership follow-up (2026-09-10): the 5,068-line entrypoint's 108 function
bodies now reside in command families and shared CLI mechanics. Setup,
workspace, source, theme, variant, maintenance, preview, and tailoring each have
an owner beneath `cli/commands/`. Document build/comparison/review and project
workflow/guidance/patch/presentation responsibilities have subdirectories. The
publication adapter is in the same command tree. Root registration imports no
domain layers and defines no workflow functions. A regression gate enforces
that boundary and rejects command-owner imports of the entrypoint, including
relative imports.

This is a behavior-preserving extraction: all 108 function bodies match their
pre-extraction ASTs, all 65 help surfaces match byte-for-byte, and publication's
module body is unchanged apart from its module-path header. Adapter tests observe
the owning module rather than depending on private entrypoint helpers. Project
workflow decisions still require extraction into operation APIs; namespace
organization alone does not resolve that responsibility.

Verification for command ownership: the focused CLI/workspace and render-format
selection passed 157 tests; default discovery passed 596 tests with one skip and
five existing PyMuPDF/SWIG deprecation warnings. The isolated seven-step
`scripts/verify_repo.py` journey passed with empty stderr for every step. Seven
workspace output snapshots remained byte-identical. Live context reported ready
source data, no context issues, and `review_required` publication. The canonical
master and public candidate hashes were unchanged; the personal-site tree
remained clean on `main`. No site sync or remote operation was performed.

Project operation ownership follow-up (2026-09-10): the 1,202-line operation
module is now a package with a 44-line explicit public API and separate records,
identity, manifest, inspection, creation, and guarded-patch owners. Job evidence
and ranking live in `ops/projects/guidance.py`; shared variant catalog loading
lives in `variants.py`. Workspace code retains inventory and optional-plan
presentation. Internal project owners cannot import the public entrypoint or
workspace presentation, enforced by an architecture gate. The guide command
still coordinates its workflow; this extraction prepares that API boundary
without claiming to implement it.

All 60 project definition/state ASTs, 11 guidance function bodies, and two
catalog functions match their pre-extraction definitions. All 65 command help
surfaces and seven workspace snapshots remain byte-identical. Focused baseline
and post-extraction project checks passed 86 tests; guidance/catalog checks
passed 99 and repository/boundary checks passed 23. Default discovery passed
625 tests with one remote skip and five existing dependency warnings. The
isolated seven-step journey passed with empty stderr throughout. Evidence is
under `/tmp/cvw-project-owners-*`; reconstruction sources are retained in the
temporary directory named by `/tmp/cvw-project-owners-root.txt`.

Proposed extraction order:

1. Context, status, and recipe extraction is complete. Further reduce
   project-guide orchestration in CLI adapters using the explicit configuration
   snapshot contract.
2. Command-family extraction is complete. Keep root registration declarative
   and evolve each family's workflow/API contract independently.
3. Preview asset extraction is complete. Continue separating server transport
   and build control where new behavior would otherwise cross their boundaries.
4. Publication grouping is complete. Split correspondence, visual geometry and
   redaction out of `publication/pdf.py` as independently verified responsibilities;
   keep site transport in `ops/syncing.py`.

AST import inspection found no build-layer imports of CLI, preview, or ops and
no non-CLI module importing the CLI. Preserve those useful dependency directions
with architecture tests (now enforced). Resolve configuration once per operation into an
immutable workspace context; repeated ad hoc reads should not select mixed
configuration generations during one build.

Implemented configuration follow-up: `ConfigSnapshot` captures raw bytes,
their digest, and deeply immutable values. Build/render adapters and the build
engine pass one snapshot through their settings resolution. A file-change
regression previously selected an absent replacement theme mid-build; it now
builds with the captured generation and records its hash in both manifests.
Configurable artifact paths reject empty/non-string values and retention days
reject booleans. Invalid settings are resolved before build artifact writes;
the regression suite previously found partial files for invalid theme, preset,
theme directory, and output-path configuration. The
[configuration contract](../reference/configuration-contract.md) distinguishes
these guarantees from publication preparation/sync, lifecycle mutations,
preview selection, and other-input snapshot work.

Inspection follow-up: `context`, `bootstrap`, and `workflow` share one captured
workbench configuration through source selection, variant settings, artifact
inventories, and publication inspection. The publication inspector also captures
once when used directly. A real populated workspace reproduced mixed source,
project, review, run, and publication state after an intervening config edit.
Ten regressions now retain the same output after edit/removal, accept an explicit
snapshot, and preserve missing-source bootstrap guidance. Two more checks cover
the complete prepared-publication path. Subsequent operations see updated
settings. Workflow descriptions receive resolved workspace locations rather than
reading configuration themselves.

Status follow-up: `workspace/status.py::inspect_status` composes the shared
inventory helpers, validates its selected source, and returns data without
terminal output or writes. `StatusInspectionError.errors` retains all source
diagnostics. The CLI adapter owns output modes and exception translation; a
missing config now produces an actionable error instead of a silent failed
invocation. Status uses one workbench snapshot, honors explicit source selection,
and does not require the default build variant. Normal context/status/workflow
outputs remain unchanged in all seven recorded comparisons.

### Medium — artifact retention is not dependency-aware — partly fixed

A read-only inventory found 25 expired proposal entries. `variant gc --json`
failed because a recorded cleanup target was already missing. The run-GC preview
listed 613 candidates and 55 invalid directories at the audit snapshot; nothing
was deleted. Counts can increase as checkout tests produce runs.

The baseline lacked stale-record reconciliation and retention derived from
review dependencies. The required contract is an explicit source-run/hash
record and a cleanup plan that names the review or project protecting each run.

Implemented follow-up: variant GC now exposes an explicit remove/reconcile plan,
validates every target before deletion, rejects shared-container cleanup, and
does not re-prune kept sources. Missing targets become record-only reconciliation
actions. The live dry run reports 25 expired entries: 24 existing bundles and
one absent bundle. No live cleanup was applied. Regression tests reproduce both
stale-record failure and partial deletion before a later invalid path; all now
pass. The owning semantics are in the
[variant lifecycle contract](../reference/variant-lifecycle.md#cleanup-plan).
Run GC now retains recent runs independently per project and variant. Explicit
retained IDs protect damaged manifests, including project-scoped IDs. The plan
separates invalid candidates from invalid diagnostics and explains retention.
Python API callers receive the same root/target guards as the CLI; symlink
traversal is rejected before any deletion. Regression tests reproduce competing
project retention, invalid-run keep failures, and deletion beyond the run store.
The [artifact retention contract](../reference/artifact-retention.md) owns these
rules. Routine cleanup documentation leads with an inspectable GC plan.

Preparatory review decomposition separates bundle creation, target resolution,
DOCX import, patch interpretation, and catalog inspection under `ops/review/`.
The 943-line review module is replaced by focused owners, with its unused private
run resolver removed. The same 48 review/context/retention checks pass before
and after extraction. Command spellings are unchanged; Python entry points are
documented by the [project contract](../reference/project-contract.md#python-ownership).

Content bundles now record exact source-run identity and baseline hashes.
Run GC retains referenced sources even when their manifests are damaged, and
reports the protecting review in `keep_reasons`. Malformed source records stop
cleanup before deletion. Historical untracked bundles, custom bundles outside
the configured review store, and standalone import-draft references still need
explicit retention; automatic dependency discovery for those remains open.

### High — review imports could drift and replacement could lose edits — fixed

An actual DOCX conversion reproduced an import selecting a newer run after its
review copy was created. Imports now bind to `review-source.json`, reject changed
baseline artifacts and conflicting selectors, and require an explicit run for
untracked DOCX files. Relative project-run paths retain their full scoped ID.

An injected record-write failure reproduced loss of edited review content during
forced replacement. The bundle's four files now share a recoverable transaction;
the regression verifies byte-for-byte preservation of the existing edited bundle
on failure. Invalid selection metadata is rejected before replacement. Targets
cannot overwrite their source run or the review store itself.

The [content-review contract](../reference/review-contract.md) owns provenance,
source health, import selection, output naming, retention, and Python boundaries.
`context` and `status` expose ready/changed/missing/invalid/untracked source
states. Custom output names are read from records instead of assuming `cv.*`.

### Medium — documentation contained competing executable owners — fixed

The documentation router pointed at tracked copies under `docs/config` and
`docs/build`; the copied publication policy lacked the required visual
fingerprint. Those 13 duplicate files were removed. Links now resolve to root
configuration, rendering resources, and tracked sample inputs. A repository
contract test prevents the router from selecting shadow configurations again.
Ignored historical local data was preserved.

### High for edit preservation — proposal authoring could damage or overwrite saved edits — fixed for recoverable saves

The proposal append path used a direct write after validation. Injected partial
writes and cancellation left truncated YAML; a manual edit or deletion after the
read was overwritten or recreated. Invalid proposal/source input could create a
lock before failing, and aliased proposal or lock paths could affect files
outside their intended ownership. FIFO inputs could reach blocking reads.
These violated the authoring criterion: preserve the prior proposal or an
observed independent edit, keep source unchanged, and reject invalid input
before persistent authoring side effects.

`ops/projects/patch_authoring.py` now owns append validation, cooperative locks,
and recoverable saving. `patches.py` owns one-read proposal capture, guarded
compilation, and application. The root Python APIs and CLI verbs remain intact;
unsupported-format errors now use the shared reader's diagnostic. A captured
proposal generation supplies the storage precondition. Saves retain metadata
and permissions, and thread/process writers reread under the shared lock.
Invalid file nodes and escaped destinations fail before writes; invalid source
encoding and YAML become domain errors without exposing their payloads.

The live [proposal authoring contract](../reference/project-contract.md#proposal-authoring)
owns the exact preflight, lock lifetime, and recovery semantics. Existing lock
files remain stable rather than being removed while other writers may use them.
This does not lock the source, guarantee crash durability, or eliminate every
filesystem race.

Verification used public temporary fixtures. The initial fault tests produced
14 intended failures; later source-decoding and node checks reproduced two and
four further failures before their fixes. The focused implementation suite
passed 121 tests. The final full-suite and operator evidence are recorded below.
The first full run exposed one CLI assertion still expecting the old
unsupported-format wording; the test now expects the shared reader diagnostic.
No production fallback or test bypass was added.

The final full suite passed 1,046 tests with one existing opt-in integration
skip and five upstream warnings in 113.07 seconds. Evidence:
`/tmp/cvw-proposal-authoring-full-final.log`. The slice's handoff decision is
**pass** for recoverable proposal authoring; product and release readiness
remain subject to the separate acceptance work below.

The final focused CLI, authoring, docs, context, and import-boundary checks
passed 78 tests. The seven standard CLI journeys passed with empty stderr. A
separate five-step CLI journey authored a project summary, rendered the
proposal, applied it, rebuilt the accepted result, and rejected stale repeat
application. Only the intended source file changed during application; the
proposal and unrelated operator file were retained. Evidence:
`/tmp/cvw-proposal-authoring-final-contracts.log`,
`/tmp/cvw-proposal-authoring-journey.json`, and
`/tmp/cvw-proposal-authoring-operator.json`.

Ruff, formatting, all pre-commit hooks including the secret scan, and changed
Markdown link-target checks passed. The canonical DOCX and public candidate PDF
retained their SHA-256 hashes; context reports ready source, no issues, and
publication `review_required`. The private inventory comparison observed one
Word temporary owner file disappear and its parent directory metadata change;
no retained file metadata changed, and 8,316 entries remained. The authoring
and verification commands did not target that owner file. The site worktree remained
clean; no remote state was refreshed or changed.

The completed slice protects the editing workflow. The
[product readiness checkpoint](2026-09-10-product-readiness-checkpoint.md)
connects it to document quality, source authority, and a finite next phase.

### Medium — generated contact information lacked usable links — fixed across document formats

A fresh build from copied configured facts produced zero PDF link annotations
and zero DOCX hyperlink elements. The header displayed long profile URLs over
two lines. This failed the document utility criterion: selected email/profile
contacts should be directly usable and readable in the generated resume or
cover letter. The authored public CV already had three working profile links
and a balanced header; it was not the target of this formatter change.

`build/contacts.py` now owns contact selection, literal labels, and explicit
link destinations shared by both document types. The Markdown composer routes
to that owner; themes retain styling ownership. Selected unsafe/non-web profile
destinations, credentials, malformed bare email values, and URI whitespace fail
in planning before writes, without echoing their values. Excluded contacts stay
excluded. This is render preflight, not remote URL validation or a new public
publication policy. The live [contact presentation contract](../howto/styling.md#contact-presentation)
owns the supported behavior. The preview iframe also now has the accessible
name `Document preview`, verified in the live browser.

The initial 12 checks reproduced 11 failures before implementation; a further
bare-email case reproduced a prefixed-mailto error before its fix. The focused
suite passed 38 tests. The full suite passed 1,060 tests, with one existing
opt-in integration skip and five upstream warnings, in 118.94 seconds. All seven
CLI verification journeys passed with empty stderr, including review packaging
and DOCX import. Evidence: `/tmp/cvw-contact-links-red.log`,
`/tmp/cvw-contact-email-red.log`, `/tmp/cvw-contact-links-focused.log`,
`/tmp/cvw-contact-links-full.log`, and `/tmp/cvw-contact-links-journey.json`.

The real generated CV now has four PDF/DOCX contact links, four pages, and 45
PDF bookmarks. Its body Markdown is byte-identical from the first section
onward. All four rendered PDF pages were inspected. The preview DOM preserved
four correct contact destinations at 961- and 500-pixel viewports, with no page
or document overflow; Chrome DevTools reported no warnings or errors. The
browser clamped the requested narrower window to 500 pixels, so this is not a
claim about smaller mobile screens. The generated DOCX retains its 104
paragraphs and heading-style counts. Neither PDF lane has a structure tree;
the authored document's direct-formatting and heading-navigation gaps remain.

The isolated workspace and its private evidence are identified by
`/tmp/cvw-document-quality-workspace.json`. Browser evidence is beneath that
workspace's `var/runs/preview/document-quality-review/`; PDF pages and OOXML
measurements are under `evidence/`. The audit tabs and its preview server were
closed; the preexisting authored-CV review tab/server were left available.
Configured source-file hashes, the canonical DOCX hash, and the public PDF hash
were unchanged. The private repository inventory retained all 8,316 entries
with identical recorded metadata. Context remained ready, with no issues and
publication `review_required`; the site worktree was clean. No remote check,
site sync, or publication approval was performed.
The slice handoff is **pass** for contact usability. The
[product checkpoint](2026-09-10-product-readiness-checkpoint.md#document-quality-follow-up)
records the next reader-facing issues: labeled teaching values, separated entry
metadata/prose, and semantic authored-document styles.

### Medium — entry metadata ran into prose and teaching values lacked labels — fixed

Rendered education, publication, conference, honor, service, teaching, and
reference records treated adjacent metadata and prose lines as one paragraph.
Teaching enrollment/evaluation values appeared without labels. This failed the
reader-facing criterion that metadata can be distinguished from narrative and
that numeric values identify their meaning. `build/entry_layout.py` now owns
compact metadata rows and separate nonempty prose blocks; domain field meaning,
selection, heading levels, and stable IDs stay in the section builders.
Teaching uses explicit `Enrollment` and `Evaluation` labels. The live
[entry structure contract](../howto/styling.md#entry-structure) owns these rules.

After correcting the test fixture to preserve frozen variants and inspect
Pandoc's actual section elements, ten expected rendering/label checks failed
before production changes. HTML paragraph checks now cover seven entry types
and optional teaching values. The real DOCX contains distinct narrative
paragraphs, and the PDF shows the expected labels. A fresh build from copied
configured facts retained four pages, 45 PDF bookmarks, and four contact links;
the first rendered PDF page was byte-identical to the preceding reviewed build.
The remaining pages and the HTML education/teaching entries were visually
inspected. Preview had no horizontal overflow or console warnings/errors.

### High for workflow utility — real DOCX edits could not become guarded patches — fixed for shared syntax normalization

The real export/edit/import check found `review_diff_only` for a supported
Experience bullet change and for an unchanged DOCX. Pandoc's default setext
headings were not recognized by the review parser; equivalent link notation
also differed from the canonical Markdown. This contradicted the documented
supported-edit and verified-no-op outcomes despite the existing tests passing.
The underlying failure existed independently of paragraph presentation.

`ops/review/markdown.py` now owns conversion and shared Markdown normalization.
Canonical and imported text use the same Pandoc writer before conservative
comparison. Original fallback diff text, stable source targets, and expected
old text remain intact. Actual DOCX checks now prove three outcomes: a real
bullet edit gives one guarded operation and `ready`; no edits gives zero
operations and `ready_no_changes`; a changed link destination remains
`review_diff_only`. Normalization failures are checked before draft allocation;
a controlled failure initially left a partial import and now preserves the
complete draft inventory. Later import writes are not a group transaction.
See the live [comparison contract](../reference/review-contract.md#markdown-comparison).

The DOCX fixture edit preserves XML namespace declarations; the first test
attempt used a serializer that changed them and was corrected before drawing
conclusions about the importer. After that correction, the meaningful red
round-trip checks failed twice, with the changed-link rejection already passing.
The combined targeted rendering/review checks passed 41 tests. Evidence:
`/tmp/cvw-entry-layout-red-confirmed.log`,
`/tmp/cvw-entry-layout-roundtrip-red.log`,
`/tmp/cvw-review-normalization-preflight-red.log`, and
`/tmp/cvw-entry-layout-focused.log`.

### Medium — verification accepted a failed editing round trip — fixed with semantic acceptance

The seven-step harness previously accepted an unchanged imported document if
its output files existed. Its own success fixture reported `review_diff_only`.
The harness-engineering pass uses the autonomy-hardening lane with
`architecture-invariants` (the unchanged import must be a no-op) and
`knowledge-integrity` (the live verification contract must state that threshold).
The intervention changes false acceptance, not command count or output styling.

The import check now requires `draft.json` to report `ready_no_changes` and name
its patch, with `project-ops` format and zero operations. The result records
that verified status. Three controls—review-only status, nonempty operations,
and wrong format—were falsely accepted before the change and are rejected now.
The focused harness/docs/boundary suite passed 43 tests. The
[verify contract](../reference/verify-contract.md#required-evidence) owns the
acceptance rule; no new runtime policy or external-state authority was added.
Evidence: `/tmp/cvw-review-harness-red.log` and
`/tmp/cvw-review-harness-green.log`.

Final verification passed 1,078 tests, one existing opt-in skip, and five upstream
warnings in 136.64 seconds (`/tmp/cvw-entry-layout-full-final.log`). The final
33 docs/context/import-boundary checks passed. Three independent seven-step CLI
runs passed with empty stderr and `ready_no_changes`; canonical Markdown,
generated Markdown, and preview HTML were byte-identical across those runs.
Evidence: `/tmp/cvw-entry-layout-repeat-{1,2,3}.json`,
`/tmp/cvw-entry-layout-repeat-comparison.json`, and
`/tmp/cvw-entry-layout-contracts-final.log`. The harness skill audit passed.

The private review workspace is identified in `/tmp/cvw-entry-layout-workspace.json`;
PDF pages and structural measurements are under its `evidence/`, with browser
screenshots/snapshots under `var/runs/preview/entry-layout-review/`. The audit
preview server and tab were closed; the original authored-CV review remains
available. Source-file hashes, the canonical DOCX hash, and the public PDF hash
were unchanged; all 8,316 private repository entries retained their metadata.
Context reports ready source, no issues, and publication `review_required`.
The site worktree is clean. No push, site sync, publication approval, or remote
advisory check occurred. The handoff decision is **pass** for entry structure,
DOCX syntax normalization, and the strengthened no-op verification gate.

### Medium — preview controls displaced the document — fixed with progressive disclosure

The live preview put every settings and diagnostic group above the document at
narrow widths. At 961 × 800, the document began at 1,066.7 pixels; at 500 × 800,
it began at 1,202.5 pixels. An initial browser acceptance check requiring 300
visible document pixels failed with zero. This obstructed the primary task of
reviewing the generated document.

The existing presentation assets now provide a quieter sidebar and compact
stacked controls. Active project, variant selection, formats, actions, status,
errors, and project warnings remain visible. Native closed-by-default disclosures own secondary
settings and build details; there is no new drawer state or framework. A viewport
declaration, keyboard skip link, semantic region names, stronger control borders,
and 44-pixel main controls improve navigation. Stable `data-cvw-*` hooks and the
rendering API remain intact. The document theme still owns document typography.

Live keyboard testing exposed a related defect after adding disclosure headings:
pressing `r` on a focused summary caused one render request. Including summaries
in the existing interactive-control guard reduced that count to zero, while
Enter still opened and closed the disclosure. Expanding build details preserved
both the frame URL and build id. Synthetic warning/error checks confirmed that
messages remain visible with details closed and warning markup remains literal.

Final browser measurements with the modern document preset:

| Viewport | Document top | Initially visible document height |
| --- | --- | --- |
| 1,440 × 900 | 24 px | 852 px |
| 961 × 800 | 421 px | 379 px |
| 500 × 800 | 413 px | 387 px |
| 375 × 812, mobile | 413 px | 399 px |
| 320 × 800, mobile | 413 px | 387 px |

No inspected viewport had horizontal shell or HTML-document overflow. All format
labels fit on one line. Measured muted-text contrast was 9.17:1; inactive button
text was 12.38:1 and control borders against their fill were 4.04:1. Real preset
changes rebuilt successfully; Markdown, PDF, and HTML switching worked. The
browser reported no warning/error messages or external shell resource requests.
These observations do not establish complete accessibility, screen-reader
compatibility, or PDF reflow behavior. Expanded content can require scrolling.

Verification: 34 baseline checks, 82 focused preview/documentation checks, and
1,078 full-suite tests passed, with one existing opt-in integration skip and five
upstream warnings. The seven-step isolated CLI harness passed with empty stderr.
The final project-identity layout refinement passed 50 preview/documentation
checks and repeated all five viewport measurements. Stop visibly disabled the
controls and both owned preview processes exited successfully. Commit hooks,
including the hardcoded-secret scan, passed.
Evidence: `/tmp/cvw-preview-layout-{baseline,focused,regression,full}.log`,
`/tmp/cvw-preview-layout-journey.json`, and the isolated fixture's
`var/runs/preview/compact-controls-review/` screenshots, snapshot, and metrics.
The original source facts, authored CV, prepared public PDF, and website remain
unchanged. No publication approval, site sync, remote push, or advisory refresh
belongs to this slice.

### High — private PDF object text survived preparation — fixed with shared disclosure inspection

Synthetic PDFs containing a forbidden phone number only in a bookmark title or
structure-element alternative text passed preparation and artifact validation.
The number remained in the prepared PDF objects while page text contained none.
Page-text checks and the existing scrub operation did not cover these strings.

`ops/publication/object_text.py` now owns decoding PDF object strings through
MuPDF's parser. Nested arrays/dictionaries, indirect values, and PDF text
encodings feed the existing phone, email, and forbidden-section checks. Path and
captured-byte validation share the same boundary. Preparation stops before
replacing publication files when those strings retain private values; it does
not guess how to rewrite reading-order content. Public bookmark and alternative
text preservation has a positive control. Raw stream bytes are outside this
inspection, and this is not a general malware or steganography assessment.

The navigation check also found accepted external bookmark destinations. Further
negative controls showed that a destination summary could omit inline JavaScript
or a chained action. Validation now checks the underlying bookmark action as
well: grouping nodes or a single internal GoTo are allowed; unsupported,
external, chained, and additional actions fail closed. This change concerns
bookmarks; existing visible page-link target and hitbox rules remain separate.

The initial object-text run failed 16 cases with one public-structure case already
passing. Two external-destination cases and four hidden/chained-action cases
also failed before their fixes. The final focused publication, sync, CLI, and
documentation run passed 134 tests. Evidence is in
`/tmp/cvw-pdf-semantic-leak-probe.json` and
`/tmp/cvw-document-semantics-{red,green,actions-red,actions-green,action-details-red,final-targeted}.log`.
The live [publication contract](../reference/publication-contract.md#non-page-disclosure)
owns the limits and recovery guidance.

Final verification passed 1,102 tests with one existing opt-in integration skip
and five upstream warnings. The seven-step isolated CLI journey passed with
empty stderr; lint, formatting, repository-contract checks, and pre-commit hooks
passed. Evidence: `/tmp/cvw-document-semantics-complete-suite.log`,
`/tmp/cvw-document-semantics-journey.json`, and
`/tmp/cvw-document-semantics-hooks.log`. Current publication status remains
`review_required`; no remote checks or site writes were performed.

### Medium — authored headings lacked semantic styles — review copy verified, promotion pending

The configured authored document had 90 default/direct paragraphs, 31 list
paragraphs, no outline levels, and no tracked changes or comments. An isolated
copy now gives the title and nine exact section headings named Word styles.
The first styled export moved teaching rows between pages. A second style-name
experiment reproduced the drift; the cause was contextual spacing, whose effect
depends on adjacent paragraphs sharing a style. The accepted copy makes the
previously suppressed spacing explicit only at changed same-style boundaries,
while retaining spacing at transitions into list paragraphs.

All three final pages match a fresh original Word export pixel-for-pixel at
96 DPI, with identical text and link positions. The strict glyph and graphics
comparison passed. DOCX wording and unrelated ZIP members are unchanged, and
the declared style/spacing changes can be reversed to recover the original
document XML. The private review folder contains the DOCX, PDF, change log, and
fidelity report; `/tmp/cvw-document-semantics-workspace.json` identifies it.

The tested local Word export produces three pages and three links, but no
bookmarks or structure tree, from both original and styled inputs. Heading styles
therefore do not prove PDF accessibility. A supported local export path with
verified structure remains follow-up work. The canonical source, prepared public
PDF, and website are unchanged; no publication review or source promotion was
declared. Word exports were restricted to exact temporary document copies. A
file-access prompt on an existing temporary PDF was canceled; fresh output names
allowed local export without changing application permissions.

## Verification and limits

Baseline: 326 tests passed, one opt-in remote PR integration test skipped. The
seven-step isolated CLI journey passed. Targeted red/green evidence covers
artifact recovery, policy bypass, graphics validation, link preservation, review
discovery, documentation ownership, and real local HTTP attacks and normal use.
Raw local evidence is recorded under `/tmp/cvw-*.log`, with visual artifacts
under the configured private `var/reviews/publication/` tree.

Final verification: 348 tests passed; the same opt-in remote integration remained
skipped. Five existing PyMuPDF/SWIG import deprecation warnings remain visible.
The isolated seven-step CLI journey passed again, as did Ruff and pre-commit
checks including gitleaks. The local public review page loaded all three page
images without horizontal overflow or browser warning/error messages. The
prepared PDF retains all three approved profile links. Pre-commit hooks were
installed in this checkout; verification used cached tools with Git HTTPS fetches
disabled.

Distribution/presentation follow-up: 350 tests passed with the same skip and
upstream warnings; the seven-step CLI journey and repeated ergonomics harness
passed. Ruff and all pre-commit checks, including secret scanning, passed.
Browser review confirmed
the sample document loaded, Rebuild advanced the build ID, and there was no
horizontal overflow, warning, error, or additional presentation-asset request.
Evidence is under `var/runs/preview/2026-09-10-resource-audit/`, with test and
journey logs at `/tmp/cvw-architecture-final-*`. The canonical DOCX hash and the
personal site's clean Git state were rechecked unchanged.

Publication lifecycle follow-up: 370 tests passed with one opt-in remote test
skipped and the same upstream warnings. The seven-step CLI journey, three-run
ergonomics harness, Ruff and all pre-commit checks passed. The ergonomics harness
initially caught a missing plain-text status field; explicit plain/JSON status
regressions now cover that failure. Record tests cover missing/boolean schema
versions, changed inputs, wrong review hashes, packet/PDF disagreement, damaged
images, preserved review on identical preparation, and private file permissions.

The actual local CV candidate was prepared again from its existing review copy.
Its PDF hash stayed `556d1db9bf900aa4ea83156e3b1881647627e2e0a760f40d899e461ddfa7e712`,
with three pages and three retained profile links. Status reports
`review_required`; no review was declared and no site sync occurred. Browser
inspection loaded all three page images without overflow or console warnings.
Evidence is under `var/runs/preview/2026-09-10-publication-lifecycle/`, with
validation logs at `/tmp/cvw-publication-*`. The canonical master DOCX and site
checkout were rechecked unchanged.

Artifact-retention follow-up: the full suite passed 388 tests with the same
opt-in skip and five upstream warnings. A subsequent absolute-symlink-root
regression and the run/repository contract tests passed together (18 checks).
Red/green logs are under `/tmp/cvw-retention-*`. The live dry runs report
25 proposal actions, including one record-only reconciliation, and 16 retained
runs across project/variant scopes. No private artifact cleanup was applied.
Ruff and secret-scanning commit hooks passed. That pass preceded the recorded
content-review lifecycle described above.

Content-review lifecycle follow-up: 412 tests passed, with the same one opt-in
remote integration skip and five upstream warnings. The seven-step isolated
CLI journey passed. Real DOCX conversion tests demonstrate import remaining on
its original baseline after a newer build, while counterfactual tests cover
changed sources, conflicting selectors, malformed records, unsafe targets,
and restoration of edited bundle bytes after a replacement failure. Ruff and
pre-commit checks passed. Evidence is under `/tmp/cvw-review-*`; the final full
suite log is `/tmp/cvw-review-verified-tests.log`. The live workspace still
reports the public CV as `review_required`; canonical master and site Git state
were rechecked unchanged. No live review bundle or private run was replaced.

Workspace/recipe extraction follow-up: 415 tests passed, including the installed
wheel journey, with the same one opt-in remote integration skip and five
upstream warnings. All seven deterministic CLI snapshots were byte-identical
after extraction: full, compact, explicit-source, and strict-failure context;
workflow; bootstrap; and status. The separate seven-step build/review journey
passed with empty stderr. New API tests verify quiet, repeatable, read-only
inspection and strict exceptions; architecture tests enforce import direction.
Existing no-reload tests now observe real source-file reads. An AST comparison
confirmed equivalent bodies for 167 definitions after owner/name changes,
excluding the intentional strict-error adapter change and recipe decomposition.
Evidence: `/tmp/cvw-workspace-full.log`, `/tmp/cvw-workspace-journey.json`, and
the before/after workspace named by `/tmp/cvw-workspace-contract-root.txt`.

Publication handoff follow-up: 434 tests passed, including the installed-wheel
journey, with one opt-in remote integration skip and the same five upstream
warnings. The 92 targeted publication/sync/CLI checks passed. Red/green tests
reproduced source replacement after planning, inconsistent signature/hash reads,
and a real preparation/review generation change. Fifteen malformed-manifest
cases that the earlier validator accepted now fail. Local evidence is under
`/tmp/cvw-sync-*`, `/tmp/cvw-artifact-*`, and `/tmp/cvw-manifest-*`; the final full
suite log is `/tmp/cvw-publication-boundary-full.log`. The live authored PDF
remains `review_required`; only temporary sites were written during validation.
The seven-step isolated journey passed with empty stderr; its summary is
`/tmp/cvw-publication-boundary-journey.json`. Canonical master and public
candidate hashes remained unchanged, and the personal-site checkout was clean.

Configuration/discovery follow-up: the corrected default suite passed 540 tests
with one opt-in remote integration skip and the same five upstream warnings.
Default collection omitted zero test-bearing files in three consecutive checks,
down from 13 omitted build-domain files. The full log is
`/tmp/cvw-configuration-inclusive-final.log`; collection red/green evidence is in
`/tmp/cvw-discovery-*.log`. Configuration regressions prove one workbench read
per build/render invocation, immutable captured values, correct config hashes
despite file edits, and no build artifacts for invalid render/path settings.
Their red/green logs are `/tmp/cvw-config-*.log`. Additional cases reject
malformed source paths and explicit optional render settings with field-specific
errors. Shared YAML aliases remain compact in both immutable snapshots and
independent mutable exports; a 25-level alias graph retains 26 containers in
each representation rather than expanding repeated subtrees.

The seven deterministic context/workflow/bootstrap/status snapshots remained
byte-identical. The isolated seven-step journey passed with empty stderr;
its summary is `/tmp/cvw-configuration-journey.json`. Ruff checks and the
harness-engineering skill audit passed. The site and canonical source remain
outside this implementation scope; the live publication is still
`review_required`.

Inspection snapshot follow-up: 552 tests passed in the inclusive default suite,
with one opt-in integration skip and the same five upstream warnings. The 161
targeted checks passed, and all seven recorded CLI outputs remained byte-identical.
Evidence: `/tmp/cvw-inspection-config-red.log`,
`/tmp/cvw-inspection-config-green.log`, `/tmp/cvw-inspection-targeted.log`, and
`/tmp/cvw-inspection-full.log`.

Status API follow-up: 559 tests passed in the inclusive default suite, with the
same one skip and five upstream warnings. The 57 targeted checks and seven-step
isolated journey passed; journey stderr was empty. Six initial RED cases covered
the missing API, missing-config diagnostic, and mixed status settings after
config edit/removal. Evidence: `/tmp/cvw-status-red.log`,
`/tmp/cvw-status-green.log`, `/tmp/cvw-status-targeted.log`,
`/tmp/cvw-status-full.log`, and `/tmp/cvw-status-journey.json`.

Artifact-name follow-up: the inclusive suite passed 594 tests with one opt-in
integration skip and the same five upstream warnings. The initial 103 targeted
checks passed after validation was added, and the full suite includes the
promotion rejection check. A separate real build with `Example résumé CV` as
its output stem produced matching files and manifest hashes in both run and
dist directories. All seven CLI snapshots remained byte-identical. Evidence:
`/tmp/cvw-artifact-names-green.log`, `/tmp/cvw-artifact-names-full.log`, and
`/tmp/cvw-readable-output-evidence.json`.

Useful verification commands:

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run python scripts/verify_repo.py --json
uv run cvw context --json --compact
uv run cvw variant gc --json
uv run cvw runs gc --json
uv build --offline --out-dir var/audit/package-check
```

Variant GC now returns a reviewable dry-run plan; exit code 2 denotes pending
actions. A wheel build alone is not the installed-package test.
No remote publish, PR integration, dependency-advisory refresh, or external URL
ingestion was performed under the repository's local-only policy. URL ingestion
validates the initial address before delegating to a redirect-capable fetcher;
redirect destination and DNS-rebinding checks remain a separate network-boundary
review item. No exploit against an external destination was attempted.

## Recommended next increment

Use the dated [product readiness checkpoint](2026-09-10-product-readiness-checkpoint.md)
for the next phase: review real document quality and workflow clarity, verify
source/configuration authority at consequential actions, then define preview
and standalone-draft retention. The live [overview](../concepts/overview.md)
routes the generated-document and authored-CV workflows separately.

Prioritize reproducible defects that obstruct those outcomes. Further module
splits, more tests, and complete filesystem snapshots are not goals on their
own. Keep the website on hold until the selected public PDF is reviewed; remote
security verification and release gardening remain a subsequent phase.
