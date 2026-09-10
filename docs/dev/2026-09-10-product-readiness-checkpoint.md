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
publish**. Completion is a useful, approved document with a repeatable revision
path. More modules, tests, or audit findings are not completion criteria.

## Readiness by user journey

| Journey | Verified support | Remaining acceptance |
| --- | --- | --- |
| Generate and inspect a useful document | Concise contact links, readable paragraphs, stable pagination; preview controls keep the document visible at inspected narrow widths | Review real wording and appearance; no full accessibility conformance claim |
| Explain and revise a cover letter | [Selection evidence](../reference/selection-contract.md) describes the chosen letter's paragraphs and tag decisions; manual revision/rebuild retains prior run evidence | DOCX letter imports remain review-only comparisons; accepted wording is edited manually in source |
| Return supported Word edits to the right source | Guarded bullet patches, unchanged-import no-ops, shared [source selection](../reference/patch-application.md#source-selection), explicit version pins | Broader editing coverage remains limited to supported operations; no bidirectional authored-CV conversion |
| Create and compare a source experiment | [Pack initialization](../howto/sot-versions.md#initialization-contract) creates a separate validated copy; comparison includes snippets and machine-readable JSON; [lifecycle recovery](../howto/sot-versions.md#lifecycle-contract) preserves baselines and selection after failed writes | Fresh destination and regular files required; configuration selection remains deliberate; source-schema validation and concurrent-writer limits remain explicit |
| Keep edits and their baselines recoverable | Expected-content guards and shared recoverable writes; [draft dependencies](../reference/artifact-retention.md#import-draft-dependencies) preserve exact source runs | No universal concurrent-writer or crash-durability guarantee; preserve ambiguous legacy imports |
| Publish exactly the reviewed public CV | [Captured inputs](../reference/publication-contract.md#input-lifetime), disclosure checks, source freshness, artifact hashes, and exact-PDF review | Current candidate requires human review; site update remains on hold |

## What the current work buys

`sot init` closes a concrete workflow gap: a flat source can now become an
independent version experiment without manual directory construction or changes
to the original source/configuration. A real CLI journey created the pack,
cloned a version, revised a paragraph, compared and activated it, then built and
explained the revised letter. The source and initial version remained unchanged.

The existing `ops.sot_versions` API routes to separate initialization, lifecycle,
comparison, copying, and result owners. Input-owned name constraints, selection
records, and directory containment are shared by readers and operations. Schema
validation and recoverable writes retain their existing owners. This keeps
policy changes out of CLI adapters and avoids parallel storage implementations.

The lifecycle audit reproduced invalid activation targets, linked selection
reads/writes crossing the pack boundary, partial selections after write failure,
and partial clones after copy failure. Shared input checks and recoverable writes
now protect these boundaries. Twenty-three lifecycle cases cover malformed
records, unsafe sources, destination conflicts, permissions, observed concurrent
edits, and injected I/O failure/cancellation. The shared source-capture extraction
passed the same 51 checks before and after its move.

A real CLI journey cloned an experiment, rejected an invalid activation while
retaining the prior selection, compared the revised paragraph, then activated,
built, and explained the letter. Source, base, and configuration stayed unchanged.
This establishes the intended editing path and bounded recovery behavior; it
does not establish source locking or crash durability.

The final code suite passed **1,240 tests**, with one existing opt-in integration
skip and five upstream warnings. The seven-step isolated CLI harness also passed.
Evidence: `/tmp/cvw-lifecycle-full.log`,
`/tmp/cvw-lifecycle-harness.json`, and `/tmp/cvw-lifecycle-journey.json` (the latter
locates the real journey workspace and logs). Earlier retained evidence includes
`/tmp/cvw-cover-letter-journey.json`, `/tmp/cvw-draft-retention-import-journey.json`,
and `/tmp/cvw-publication-authority-real-journey.json`. These are local session
artifacts; live contracts above remain the durable behavior authority.

Before/after inventories confirm unchanged regular-file paths and bytes under
`local/` and `var/`, along with unchanged canonical master and public PDF hashes.
Context reports a ready source with no issues and publication still requiring
review. `/tmp/cvw-lifecycle-invariants.json` records those checks. The website
working tree remains clean; no source promotion, site sync, or push occurred.

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

The public PDF has no bookmarks, document language, or structure tree; the
generated PDF also lacks a structure tree. An unpromoted authored Word copy
with title/heading styles preserved three-page rendering, text, and links, but
did not establish tagged export. That copy contains private material and is not
the sanitized public artifact. The installed Word AppleScript `save as` interface
exposes no tagging option. A faithful, accessible PDF export remains unresolved.

The [non-page disclosure contract](../reference/publication-contract.md#non-page-disclosure)
covers decoded PDF object strings and bookmark actions. Opaque streams and
general malware assessment remain outside that claim.

An isolated review packet, preservation proposal, PDF observations, and browser
evidence are located by `/tmp/cvw-release-review-workspace.json`. The copied
public PDF retains hash `556d1db9bf900aa4ea83156e3b1881647627e2e0a760f40d899e461ddfa7e712`.
No review receipt, source promotion, or site update was performed.

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

Remote advisory checks, branch consolidation, pushing, and site sync belong to
the release phase; local tests cannot establish zero remote vulnerabilities.
Additional refactors need a demonstrated workflow failure, maintenance cost,
or privacy risk. Nonblocking ideas belong in follow-up work, not an expanding
release checklist.
