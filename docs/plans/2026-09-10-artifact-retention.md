---
id: plan-2026-09-10-artifact-retention
intent: Preserve editing provenance while making generated workspace clutter reviewable.
audience: [operator, maintainer]
status: historical
navigation:
  parent: ../readme.md
---

# Artifact retention implementation plan

This is a working decision record, not an implemented cleanup contract.
The live [retention contract](../reference/artifact-retention.md) remains
authoritative. No live files were deleted during this audit.

## Why this work matters

The useful outcome is a smaller, understandable workspace that still explains
every outstanding edit. A saved draft must not lose its comparison baseline
merely because newer documents were built. At the observed scale, retention is
an organization and provenance problem, not urgent disk-space recovery.

The read-only September 10 inventory found 6,442 files totaling 36.2 MB under
the run store, including 198 preview files totaling 12.6 MB. Reviews contain
45 files totaling 1.6 MB; drafts contain 69 files totaling 0.35 MB. The preview
store has 37 legacy directories plus loose evidence/log files. These figures
describe this inventory only; filesystem age is not a deletion decision.

With two latest runs retained per scope, current GC lists 1,138 valid candidates,
23 retained runs, and 71 invalid directories. The single recorded import draft
has a present source and is currently retained by recency. Older review bundles
have no `review-source.json` records, so their dependencies cannot be inferred.
All five current authored-publication dependencies exist outside the system
temporary directory. Publication artifacts remain separate from run GC.

## Scope

In scope: import-draft run dependencies, a reviewable inventory, explicit keep
reasons, and acceptance criteria for future preview retention.

Out of scope: live pruning, source/document relocation, publication packet
deletion, whole-store cleanup, periodic cleanup jobs, or automatic decisions
about legacy review evidence. Existing project proposal expiration remains
owned by [variant lifecycle](../reference/variant-lifecycle.md).

## Evidence-backed finding

**Run cleanup can strand an import draft.** In isolated workspace and project
fixtures, a newer build displaced the imported source from the keep window.
Both dry-run plans selected that source for removal; confirmed cleanup deleted
it while preserving the draft. The draft then lacked its canonical comparison
baseline. The current live import happens to be recent enough; that does not
establish dependency retention.

Evidence: `/tmp/cvw-retention-dependency-probe.json`. Existing retention, preview,
and clean checks passed 23 tests; another 23 content-review provenance tests
passed, including existing review-pack protection. Documentation checks passed
31 tests and repository hooks passed. Inventory and current-plan summaries
are in `/tmp/cvw-retention-inventory.json`,
`/tmp/cvw-retention-runs-before.json`, and
`/tmp/cvw-retention-publication-dependencies.json`.

## Retention decisions

| Artifact | Decision |
| --- | --- |
| Run referenced by a content review record | Keep under the existing contract, including a damaged baseline |
| Run referenced by an import draft | Keep independently of recency, manifest health, canonical-byte freshness, or `apply_status`; implement this guard first |
| Import draft itself | Keep until an explicit draft decision; `ready_no_changes` is not deletion authorization |
| Registered proposal variant | Use its existing keep/discard and expiration owner |
| Legacy preview folder, screenshot, or log | Manual review; do not infer disposability from its name or modification time |
| Authored source, public PDF, or publication packet | Preserve under the publication lifecycle; exclude from run/preview cleanup |

## Ordered work

- [x] Inspect live stores without writes and capture current GC decisions.
- [x] Reproduce loss of standalone draft dependencies in disposable fixtures.
- [x] Add import-draft source discovery under the content-review owner and use
  it in run GC. Keep parsing out of CLI presentation and avoid a second metadata
  interpretation inside the run catalog.
- [x] Re-run the live dry-run. It now refuses ambiguous imports instead of
  presenting an unsafe candidate set.
- [ ] Reconcile legacy imports and reviews with explicit retained IDs before
  considering any removal; no live cleanup is authorized by this plan.
- [ ] Reassess preview retention after durable invocation metadata exists. Keep
  current legacy evidence outside automatic cleanup eligibility.

## Import dependency implementation contract

The implemented slice extends run retention to standalone imports; it does not delete
drafts or add a new cleanup subsystem.

Done criteria:

1. Recognized import records under the configured draft store retain their exact
   canonical source run, for both workspace and project runs. The JSON plan
   explains retention with `draft:<draft-id>` alongside existing keep reasons.
2. Missing/damaged source artifacts still retain the source directory for
   recovery. Retention does not require a successful import or fresh content.
3. Malformed or ambiguous import metadata stops cleanup before deletion. Validate
   the declared source kind, normalized run identity, and canonical path; never
   substitute the newest run. Path/ID disagreement is an error.
4. The metadata reader belongs to `ops/review/`; `ops/runs.py` consumes its source
   references. Use one captured workbench configuration for a GC request.
5. Planning leaves all files unchanged. In disposable fixtures, confirmed GC
   removes an unrelated eligible run and preserves every referenced run. Unknown
   legacy dependencies require explicit retention, not invented provenance.

Verification must cover normal/project/invalid runs, no-op and review-only
drafts, stale canonical bytes, malformed records, custom draft roots, and an
unrelated removable run. Exercise the existing CLI JSON plan and its exit codes.
Run retention/review regressions, workspace boundaries, repository contracts,
the full suite, and the isolated CLI harness. Preserve the current partial-I/O
cleanup limitation; this slice does not claim a concurrent-writer transaction.

## Implementation evidence

The retention reader now lives in `ops/review/drafts.py`. Ten initial failures
demonstrated missing retention; twelve further failures exposed ambiguous
identity and changing-configuration cases. The focused retention, review, CLI,
and documentation group passed 102 tests. The live dry-run stops because 20
legacy import folders have no `draft.json`; no live files were removed.
Those records must not be fabricated from current hashes.

The seven-step isolated CLI harness passed. A follow-up used its real DOCX
import, built a newer run, and selected a different empty review store. GC then
retained the old comparison baseline solely through `draft:<draft-id>`, with
zero removals. This follow-up changed only the owned harness workspace.

Final verification passed 1,165 tests, one existing opt-in integration skip,
and five upstream warnings. Lint/format checks and repository hooks passed.
The full log is `/tmp/cvw-draft-retention-full.log`; harness results are in
`/tmp/cvw-draft-retention-journey.json`.

Evidence is retained in `/tmp/cvw-draft-retention-red.log`,
`/tmp/cvw-draft-retention-invalid-red.log`,
`/tmp/cvw-draft-retention-targeted.log`,
`/tmp/cvw-draft-retention-live-result.json`, and
`/tmp/cvw-draft-retention-import-journey.json`. The live
[import-draft retention contract](../reference/artifact-retention.md#import-draft-dependencies)
owns behavior and recovery guidance.

## Preview follow-up threshold

Do not build a deletion command around the existing legacy folders. New previews
would first need a durable invocation identity, creation/update times, scope,
and a reliable link to active-server ownership. A future planner must retain
active/uncertain sessions, explicitly kept invocations, and the configured
latest-per-scope window; unknown or malformed entries require manual review.
Only explicitly recognized invocations may become candidates.

That planner must prove unchanged inventory on dry-run, no source/run/publication
targets, and rejection when ownership changes. Adoption would start with a
reported plan and opt-in execution. With only 12.6 MB of current preview evidence,
this automation is deferred until metadata ownership and a useful cleanup need
are demonstrated. No blocking question prevents the import-dependency fix.
