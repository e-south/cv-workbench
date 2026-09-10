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
| Explain and review a cover letter | Selection records the chosen letter's paragraphs; explain reports tag decisions; review checklists include selected paragraphs; manual revision/rebuild preserves prior run evidence | DOCX letter edits remain review-only comparisons; accepted wording is edited manually in the source |
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

## How the recent fixes support the product

| Change | User value | Owning contract |
| --- | --- | --- |
| Apply to the selected source version | The document being reviewed and the source being edited refer to the same selected directory | [Source selection](../reference/patch-application.md#source-selection) |
| Capture preparation inputs and action settings | Validation and provenance describe the bytes actually processed; changed originals reject preparation before replacement | [Input lifetime](../reference/publication-contract.md#input-lifetime) |
| Retain import baselines independently of recency | Building a newer document cannot silently remove an outstanding edit's comparison source | [Draft dependencies](../reference/artifact-retention.md#import-draft-dependencies) |
| Explain the actual cover letter and review its paragraphs | Selection and checklists describe the document being revised, with clear inclusion/exclusion reasons | [Selection evidence](../reference/selection-contract.md) |

The latest code baseline passed 1,173 tests with one existing opt-in integration
skip and five upstream warnings, plus the seven-step isolated CLI harness and
repository hooks. A real import/new-build/retention journey kept its baseline
solely through its draft dependency. A separate preparation from real authored
inputs produced a public PDF byte-identical to the live candidate in an isolated
workspace. Evidence: `/tmp/cvw-draft-retention-full.log`,
`/tmp/cvw-draft-retention-import-journey.json`, and
`/tmp/cvw-publication-authority-real-journey.json`. Contract-specific concurrency
and recovery limits remain explicit; local checks are not remote advisory evidence.

The cover-letter pass reproduced a real build with 13 resume selection items,
no letter sections, and a failed `explain --id opening`. Six initial regressions
and one checklist regression now pass. A real sample build/explain/review/import/
manual-source-revision/rebuild journey preserves the original run's paragraph
text and reports revised text in the new run. The selection fix preserves
Markdown/HTML bytes, DOCX document XML, and PDF text/pixels. Full-suite and harness
evidence is in `/tmp/cvw-cover-letter-full.log` and
`/tmp/cvw-cover-letter-harness.json`; `/tmp/cvw-cover-letter-journey.json` locates
the isolated workspace and its `journey-result.json`. No live source was edited.

## Current public artifact review

A fresh inspection of the exact public candidate confirms three pages, three
contact links, and the corrected left-aligned header with concise link labels.
The local Chrome packet loaded all three page images without horizontal overflow
at 961 × 907 or console warnings/errors. Visual inspection found no clipping.
This is a layout observation, not approval of the CV's facts or audience fit.

Content review should confirm current roles, dates, and achievements, and decide
whether to change the heading “Honors and Rewards” to “Honors and Awards.” The
short standalone rule below the last section on page three is also an editorial
choice to inspect in the authored source. These are review notes, not source edits.

The public PDF has no bookmarks, document language, or structure tree. The
installed Word AppleScript dictionary exposes no tagging/accessibility option
for `save as`. A tagged export that retains the authored layout has therefore
not been established with this local path. Do not equate a successful export or
heading-style changes with an accessible PDF. Choose a supported export path
and verify reading order, tags, disclosure, and layout before claiming that outcome.

An isolated review packet, preservation proposal, PDF observations, and browser
evidence are located by `/tmp/cvw-release-review-workspace.json`. The copied
public PDF retains hash `556d1db9bf900aa4ea83156e3b1881647627e2e0a760f40d899e461ddfa7e712`.
No review receipt, source promotion, or site update was performed.

The readiness pass changed documentation only. Its 37 documentation, workspace
boundary, and context checks and all repository hooks passed. Before/after
inventories confirm identical regular-file paths and bytes under `local/` and
`var/`; the canonical master hash is unchanged as well. The existing loopback
preview serves the same public PDF. These observations are retained in the
review workspace's `final-invariants.json` and `/tmp/cvw-release-readiness-*.log`.

## Bounded remaining effort

1. **Preserve history — decision recorded.** Keep the 20 legacy imports and run
   store unchanged. Their notes identify 12 present possible baselines, but do
   not establish provenance. The [preservation proposal](../plans/2026-09-10-artifact-retention.md#legacy-preservation-proposal)
   defers cleanup; the storage cost is small and this does not block document review.
2. **Approve a useful document — current milestone.** Review the actual public
   candidate for wording and appearance. Resolve source changes through a fresh
   export/preparation cycle, then review the resulting exact artifact.
3. **Decide the PDF accessibility requirement.** Tagged, faithful export remains
   unresolved. It is required before claiming an accessible PDF; it must remain
   explicit in any release decision.
4. **Release the approved artifact — subsequent phase.** Return to website
   integration and repository gardening after the document decision.

After artifact review, return to the website and its release gardening. Remote
advisory checks, branch consolidation, pushing, and site sync belong to that
subsequent phase; local tests cannot establish zero remote vulnerabilities.
Additional refactors need a demonstrated workflow failure, maintenance cost,
or privacy risk. Nonblocking ideas belong in follow-up work, not an expanding
release checklist.
