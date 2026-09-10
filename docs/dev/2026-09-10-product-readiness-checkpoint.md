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
| Apply an edit to the selected source version | Draft and project application share one selection owner, preserve explicit version pins, and report the concrete edited directory | Publication/configuration authority is a separate remaining trace; directory selection is not a global source snapshot |
| Preserve work when a save fails | Proposal locking, expected-text/byte guards, staged rendering, and recoverable grouped writes | No crash-durability or universal concurrent-writer guarantee |
| Publish a faithful, private-data-checked CV | Separate preparation, disclosure policy, source freshness, immutable artifact hashes, and exact-PDF review; hidden object text and unsafe bookmark actions checked | Current public candidate requires human review; site update remains on hold |
| Keep the workspace understandable | Separate sources, proposals, runs, previews, reviews, and publication artifacts with concrete owners and routed contracts | Preview and standalone-draft retention need a tested plan before any live cleanup |

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

## Current slice: reliable source selection

The application audit reproduced a wrong-directory write: draft application
(both supported patch formats) and default project application could edit
leftover root files while a build selected the active version. Explicit project
overrides already selected correctly. The fix moves selection into application
operations and makes command summaries report their returned concrete directory.

A single existing input owner now rejects incomplete packs, invalid active
text, non-directory versions, and active paths escaping the pack. An explicit
version stays pinned. If `ACTIVE` changes after selection, the in-flight edit
continues against the selected directory; the next invocation selects again.
The [application contract](../reference/patch-application.md#source-selection)
owns these semantics and their concurrency limits.

Isolated regression evidence covers both CLI and Python operation paths,
root-level leftovers, explicit overrides, invalid packs with unchanged files,
and active-pointer changes. The initial wrong-directory tests failed in three
paths; the invalid-pack tests then exposed ten failures before repair.
The combined application/configuration regression passed 102 tests; the broader
application, CLI, workspace, and documentation group passed 418. Final validation
passed 1,123 tests with one existing opt-in integration skip and five upstream
warnings, plus all seven isolated CLI harness steps, lint/format checks, and
repository hooks. The live context remains ready with no reported issues.
Canonical authored-source and prepared-public-PDF hashes are unchanged, and the
website checkout remains clean.

Evidence: `/tmp/cvw-apply-authority-red.log`,
`/tmp/cvw-apply-authority-invalid-red.log`,
`/tmp/cvw-apply-authority-targeted.log`, `/tmp/cvw-apply-authority-full.log`,
`/tmp/cvw-apply-authority-journey.json`, and `/tmp/cvw-apply-authority-hooks.log`.
These are local validation records, not public release or advisory evidence.

## Bounded remaining effort

1. **Finish consequential-action authority.** Trace publication preparation and
   sync configuration/source selection. Fix only a reproduced wrong-source,
   wrong-artifact, or disclosure risk. Preserve the existing explicit review gate.
2. **Define maintenance without deleting work.** Produce a tested, reviewable
   retention plan for preview outputs and standalone drafts that preserves
   referenced runs and reviews. No live pruning in this phase.
3. **Reach the review decision.** Present the selected authored/public artifact
   and identify verified, pending-review, and deferred items. Keep the supported
   PDF-structure investigation explicit rather than treating headings as proof.

After artifact review, return to the website and its release gardening. Remote
advisory checks, branch consolidation, pushing, and site sync belong to that
subsequent phase; local tests cannot establish zero remote vulnerabilities.
Additional refactors need a demonstrated workflow failure, maintenance cost,
or privacy risk. Nonblocking ideas belong in follow-up work, not an expanding
release checklist.
