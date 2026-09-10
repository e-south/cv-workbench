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
`cli/publication.py`; lifecycle code is grouped under `ops/publication/` with
scoped owner guidance. Publication inspection and workflow description have a
workspace module shared by context and status. Broader CLI/context decomposition
below remains open.

Proposed extraction order:

1. Move context inspection and recipe construction into workspace modules with
   typed results; leave CLI parsing and output adapters thin.
2. Publication command extraction is complete. Register review, tailoring and
   build commands from their own CLI modules without changing command syntax.
3. Preview asset extraction is complete. Continue separating server transport
   and build control where new behavior would otherwise cross their boundaries.
4. Publication grouping is complete. Split correspondence, visual geometry and
   redaction out of `publication/pdf.py` as independently verified responsibilities;
   keep site transport in `ops/syncing.py`.

AST import inspection found no build-layer imports of CLI, preview, or ops and
no non-CLI module importing the CLI. Preserve those useful dependency directions
with architecture tests. Resolve configuration once per operation into an
immutable workspace context; repeated ad hoc reads should not select mixed
configuration generations during one build.

### Medium — artifact retention is not dependency-aware — partly fixed

A read-only inventory found 25 expired proposal entries. `variant gc --json`
failed because a recorded cleanup target was already missing. The run-GC preview
listed 613 candidates and 55 invalid directories at the audit snapshot; nothing
was deleted. Counts can increase as checkout tests produce runs.

[variant_lifecycle.py](../../src/cvworkbench/ops/variant_lifecycle.py) needs an
explicit stale-record reconciliation path, while preserving fail-closed deletion
rules. [runs.py](../../src/cvworkbench/ops/runs.py) retains latest/explicit run IDs
but does not derive retention from outstanding review references. Review packs
should carry a durable source-run/hash record, and cleanup should explain which
review, project, or publication protects an artifact before proposing removal.

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
rules. Durable review references remain open; routine cleanup documentation now
leads with an inspectable GC plan and explicit review dependencies.

Preparatory review decomposition separates bundle creation, target resolution,
DOCX import, patch interpretation, and catalog inspection under `ops/review/`.
The 943-line review module is replaced by focused owners, with its unused private
run resolver removed. The same 48 review/context/retention checks pass before
and after extraction. Command spellings are unchanged; Python entry points are
documented by the [project contract](../reference/project-contract.md#python-ownership).

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
Ruff and secret-scanning commit hooks passed. Durable review/run references
remain an explicit open dependency rather than an inferred retention guarantee.

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
contracts are complete. Next extract remaining context/workflow decisions from
the CLI. Follow with semantic document styles and further
owner-bounded decomposition, each behind its own behavior tests. Reconcile lifecycle records and
protect referenced artifacts before pruning the workspace. Keep the personal
site on hold until the chosen workbench changes and the exact public PDF are
reviewed.
