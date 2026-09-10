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

[atomic.py](../../src/cvworkbench/ops/atomic.py) deleted backups even when
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

Portability, preview presentation extraction, and publication freshness/review
contracts, workspace inspection, workflow-family extraction, and CLI command
ownership are complete.
Project identity now has one read owner shared by inspection and execution.
Guided creation now has a callable workflow, captured settings, and explicit
recovery. Creation cleanup now tracks directory ownership, and retarget writes
recover from ordinary I/O failures. Direct creation now preflights local inputs
and captures its job text and variant definition. Retargeting now reads one
validated manifest generation, checks for observed intervening edits, and
exposes changed saved-guidance selections. Typed descriptive metadata now has a
single parser, inventory preserves partial/invalid descriptions, and saved-plan
reads enforce project ownership. Stored job-file comparisons now expose missing,
changed, or unreadable artifacts independently of run review readiness. Shared
project inspection now supplies CLI and preview observations with explicit
configuration capture for full inspection. Retained history remains inspectable
when proposals expire or become invalid, and run packaging is independent of
current source inputs. Project builds now share a callable operation and defer
persistent run allocation until source/content/render preflight passes. Continue
with render-asset provenance, artifact recovery, and remaining apply/patch orchestration.
New guidance
now records its consumed input fingerprints and supports scoped comparisons;
historical plans retain explicit unknown provenance. Keep inventory existence,
executable proposals, recorded metadata, current artifact observations, and
review readiness distinct.

Extend explicit configuration snapshots to publication preparation/sync,
lifecycle mutations, and preview selection. Follow with semantic document styles and further
owner-bounded decomposition, each behind its own behavior tests. Extend retention
to standalone draft references and inspect historical untracked bundles before
pruning the workspace. Keep the personal
site on hold until the chosen workbench changes and the exact public PDF are
reviewed.
