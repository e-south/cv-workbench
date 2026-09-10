---
id: dev-2026-09-10-product-readiness-checkpoint
intent: Connect the hardening effort to user outcomes and a bounded next phase.
audience: [operator, maintainer]
status: historical
navigation:
  parent: ../readme.md
---

# Product readiness checkpoint — 2026-09-10

This dated decision surface explains the product value and remaining acceptance
work. The live [product overview](../concepts/overview.md) routes workflows;
the [detailed audit](2026-09-09-information-architecture-audit.md) retains earlier
findings and verification records. Runtime behavior belongs to the linked live
contracts.

## Value proposition

Maintain trusted career information, reuse it in professional documents, review
edits without losing the baseline, and publish exactly the intended artifact.
The value is less manual rebuilding, fewer ambiguous versions, useful previews,
and confidence that private source material stays private.

There are two explicit source authorities. Structured facts produce generated
resumes and cover letters; an authored DOCX controls the faithful public CV's
wording and layout. They share review and artifact-integrity principles.
Automatic bidirectional editing between these authorities is not promised.

The product should make a small sequence dependable: **choose a source → propose
an edit → preview → apply deliberately → review the exact public artifact →
publish**. More modules, tests, or audit findings are not completion criteria.

## Readiness by user journey

| Journey | Verified support | Remaining acceptance |
| --- | --- | --- |
| Generate a readable document | Concise working contact links; separate metadata and narrative paragraphs; stable generated CV pagination and first-page rendering | Review real document wording and appearance for the intended audience |
| Edit through Word and retain source authority | A real supported bullet edit returns as a guarded patch; unchanged DOCX imports are no-ops; changed link destinations require review | Broader editing coverage remains limited to documented supported operations |
| Preview without obscuring the document or changing source | Secondary settings use native disclosure; document visible at inspected narrow widths; keyboard controls and format switching verified; isolated preview outputs | Expanded settings/long warnings can require scrolling; no full assistive-technology conformance claim |
| Apply an edit to the selected source version | Draft and project application share one selection owner, preserve explicit version pins, and report the concrete edited directory | Directory selection is not a global source snapshot; expected-text/byte guards retain their documented concurrency limits |
| Preserve work when a save fails | Proposal locking, expected-text/byte guards, staged rendering, and recoverable grouped writes | No crash-durability or universal concurrent-writer guarantee |
| Publish a faithful, private-data-checked CV | Captured preparation inputs, consistent action settings, disclosure checks, source freshness, immutable artifact hashes, and exact-PDF review | Current public candidate requires human review; site update remains on hold |
| Keep the workspace understandable | Separate artifact owners; review and import drafts retain exact source runs; cleanup explains dependencies and rejects ambiguous import metadata | Twenty legacy imports need provenance/retention decisions before cleanup; preserve them; automatic preview pruning deferred |

## Document review evidence and limits

The generated CV has four pages, 45 bookmarks, and four contact links. The
entry-formatting pass separated 19 narrative paragraphs in DOCX while preserving
the first PDF page's rendered bytes. The contact and review paths were exercised
across Markdown, HTML, PDF, and DOCX in isolated workspaces.

The preview shell was checked at 320, 375, 500, 961, and 1,440 pixels without
horizontal overflow in the inspected shell/HTML. At 500 × 800, the document's top
moved from 1,202 to 413 pixels. Keyboard disclosure, shortcut guards, skip link,
real styling rebuilds, and Markdown/PDF switching passed. This establishes the
inspected local Chrome behavior, not general browser or accessibility coverage.

An unpromoted authored Word review copy has a title and nine section-heading
styles. Explicitly preserving Word's contextual-spacing behavior retained all
three pages: identical 96-DPI pixels, extracted text, and link positions relative
to a fresh original export, plus a passing strict glyph/graphics comparison.
Its wording is unchanged. The canonical source and public candidate are intact.

The tested Word export still has no bookmarks or structure tree, and the
generated PDF also lacks a structure tree. Accessible PDF structure is separate
acceptance work; source heading styles do not prove it. The authored review copy
contains private material and is not the sanitized public artifact.

The [non-page disclosure contract](../reference/publication-contract.md#non-page-disclosure)
defines what publication checks inspect and their limits. They cover decoded
PDF object strings and bookmark actions; opaque streams and general malware
assessment remain outside that claim.

## Consequential-action authority

Application could edit leftover root files while a build selected the active
version. Draft and project application now share one selection owner and report
the concrete edited directory. Incomplete packs and escaping active paths are
errors; explicit versions remain pinned. The
[application contract](../reference/patch-application.md#source-selection) owns
selection and concurrency limits. The source-selection slice passed 1,123 tests
and seven isolated CLI harness steps; its evidence remains in
`/tmp/cvw-apply-authority-*.log`.

Publication preparation and sync could combine different workbench settings
within one command. Preparation also checked DOCX/PDF correspondence before
capturing source hashes, and recorded policy/person/variant hashes after use.
A reproduced export change could therefore inherit an earlier correspondence
result. Configuration edits/removal produced eight failing API/CLI cases;
changes to the five preparation inputs produced five more failures.

Preparation and sync now use one workbench snapshot. A dedicated input owner
captures five files into private temporary copies for preparation; provenance
records their original identities and captured-byte hashes. Changes to original
inputs reject preparation before output replacement. Permissions and cleanup
on success/cancellation were verified. The
[input-lifetime contract](../reference/publication-contract.md#input-lifetime)
owns these boundaries. It does not claim a simultaneous filesystem snapshot,
writer locking, crash durability, or automatic human review.

A fresh CLI preparation from the real configured DOCX/PDF pair, with output
restricted to a new temporary workspace, produced a public PDF byte-identical
to the existing candidate. All original inputs and the live candidate were
unchanged. The isolated result remains `review_required`, with no review receipt.
Evidence is in `/tmp/cvw-publication-authority-real-journey.json`.

The focused publication, sync, CLI, and documentation regression passed 168
tests. Failure and passing evidence is retained in
`/tmp/cvw-publication-authority-config-red.log`,
`/tmp/cvw-publication-authority-input-red.log`, and
`/tmp/cvw-publication-authority-targeted.log`. The final suite passed 1,139 tests
with one existing opt-in integration skip and five upstream warnings. All seven
isolated CLI harness steps, lint/format checks, and repository hooks passed.
The live context remains ready with no reported issues, the same source selection,
and publication state `review_required`. Full evidence is in
`/tmp/cvw-publication-authority-full.log`,
`/tmp/cvw-publication-authority-journey.json`, and
`/tmp/cvw-publication-authority-hooks.log`. These are local checks, not remote
advisory evidence.

## Bounded remaining effort

Import-draft retention subsequently passed 1,165 tests (one existing opt-in skip),
the seven-step CLI harness, and a real import/new-build/retention journey. The
remaining legacy-data decisions below are explicit; validation did not remove
or rewrite historical evidence.

1. **Preserve legacy evidence.** The [retention implementation](../plans/2026-09-10-artifact-retention.md)
   now protects standalone import baselines, including stale or damaged runs.
   The live dry-run refuses 20 older imports without source metadata. Keep those
   files and reconcile historical evidence before any future cleanup; do not
   synthesize verified provenance. No live pruning is part of this phase.
2. **Reach the review decision.** Present the selected authored/public artifact
   and identify verified, pending-review, and deferred items. Keep the supported
   PDF-structure investigation explicit rather than treating headings as proof.

After artifact review, return to the website and its release gardening. Remote
advisory checks, branch consolidation, pushing, and site sync belong to that
subsequent phase; local tests cannot establish zero remote vulnerabilities.
Additional refactors need a demonstrated workflow failure, maintenance cost,
or privacy risk. Nonblocking ideas belong in follow-up work, not an expanding
release checklist.
