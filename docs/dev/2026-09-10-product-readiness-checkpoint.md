---
id: dev-2026-09-10-product-readiness-checkpoint
intent: Connect the hardening effort to user outcomes and a bounded next phase.
audience: [operator, maintainer]
status: historical
navigation:
  parent: ../readme.md
---

# Product readiness checkpoint — 2026-09-10

This is a dated assessment, not a runtime contract. Start with the live
[product overview](../concepts/overview.md) to choose a document workflow;
the [audit](2026-09-09-information-architecture-audit.md) retains detailed findings.

## Value proposition

Maintain a trusted career record, reuse it for professional documents, review
changes without losing the baseline, and publish only the intended artifact.
Success means less manual rebuilding, clear version authority, useful previews,
and confidence that private source material stays private.

There are two source authorities: structured facts support generated resumes
and cover letters; an authored DOCX controls the layout of the faithful public
CV. They share review and artifact-integrity principles, not an automatic
bidirectional editing promise.

## How the current work contributes

| User outcome | Current support | Remaining acceptance work |
| --- | --- | --- |
| Save a proposed edit without losing another edit or damaging the proposal | Dedicated authoring owner, source guards, cooperative locking, recoverable saves, useful CLI errors | Dogfood the commands and explanations with a realistic editing task |
| Preview or rebuild without altering source facts or an audited result | Separate preview outputs, staged bundles, captured build inputs and artifact manifests | Review the actual document and preview experience; fixture correctness does not establish aesthetics |
| Know which reviewed document can be published | Separate authored-publication workflow, disclosure checks, freshness status, exact-PDF review | The current candidate still requires human review; site updates remain on hold |
| Extend the product without duplicating workflow rules | Concrete operation owners, thin command adapters, shared storage, routed contracts | Extract further only for a demonstrated maintenance or workflow problem |
| Keep a workspace understandable over time | Explicit project/run/proposal identities and retention contracts | Preview retention and standalone draft references need a bounded follow-up; no live cleanup in this phase |

The proposal-authoring slice closes an edit-preservation gap. It contributes to
trustworthy editing; it does not add document types, improve the CV typography,
or prove that all workflows are pleasant to use.

## Evidence and limits

The local suite covers operation contracts, failure recovery, CLI behavior,
and installed-package journeys. The separate verification harness exercises
doctor, context, multi-format build, one-shot preview, project guidance,
review packaging, and DOCX import in an isolated workspace. Its sample import
does not substitute for reviewing and accepting meaningful real-document edits.

The authoring-to-application check uses copied sample facts and verifies that
authoring and project rendering leave source unchanged, application changes
only the intended source file, rebuilding includes the accepted text, and a
stale second application is rejected. These are functional checks, not visual
review, adversarial filesystem isolation, or remote vulnerability evidence.

Exact verification results for this slice belong to the linked audit. The
canonical authored source and prepared public candidate are preserved. No site
sync, push, publication approval, or advisory refresh is part of this checkpoint.

## Document-quality follow-up

A fresh four-format build from an isolated copy of the configured career facts
exposed plain-text profile URLs with no contact links in PDF or DOCX. The shared
[contact formatter](../howto/styling.md#contact-presentation) now emits concise,
literal profile labels and an email link. The generated document has four working
contact links, the same four pages and 45 bookmarks, and unchanged Markdown body
text. The preview frame now has an accessible name. Browser checks at 961- and
500-pixel viewports found no page/document horizontal overflow or console errors.
These checks do not establish complete accessibility or smaller-phone support.

Entry formatting now labels teaching metrics and separates education, service,
publication, conference, honor, and reference metadata from narrative paragraphs.
A fresh generated CV retains four pages, 45 bookmarks, and four contact links;
DOCX now contains 19 separate body-text paragraphs where prose had previously
merged into metadata. Its first rendered PDF page remains byte-identical.

The real edited-DOCX check uncovered a deeper workflow defect: equivalent
heading/link syntax caused supported edits to fall back to review-only diffs.
Shared Pandoc normalization now preserves a real bullet edit as a guarded patch,
recognizes an unchanged document as a no-op, and still rejects changed link
destinations from automatic application. The CLI harness now requires a no-op
with zero operations when importing its unchanged review document; existence of
an import draft no longer counts as proof of a successful editing round trip.

Remaining document work concerns semantic authored-document styles and tagged
PDF output. The authored DOCX still has 90 default/direct paragraphs and 31 list
paragraphs; the authored public PDF has no bookmarks or structure tree. The
generated DOCX has heading styles, but its PDF also lacks a structure tree.
Browser inspection also shows that the stacked preview controls consume the
first screen near the responsive breakpoint; a compact responsive-control pass
would improve access to the document itself.

The contact slice passed 1,060 tests (one existing opt-in skip), the seven CLI
verification journeys, and real resume/cover-letter link checks across HTML,
PDF, and DOCX. The detailed audit retains the evidence paths and limits. No
source facts, authored source, publication approval, or site files were changed.

The entry/review follow-up passed 1,078 tests (one existing opt-in skip) and
three independent seven-step CLI runs. Each unchanged review import reported a
verified no-op with zero operations; canonical Markdown, generated Markdown,
and preview HTML matched across runs. Source facts and publication artifacts
remained unchanged. This closes the observed rendering and DOCX round-trip gaps,
while the remaining acceptance work below stays explicit.

## Bounded next phase

1. **Document quality and workflow clarity.** The generated-document walk and
   edited-DOCX round trip now have direct evidence. Finish the bounded remaining
   work on authored-document heading semantics, PDF structure, and compact
   preview controls. Retain an inspectable output and specific acceptance checks;
   automated fidelity checks alone cannot approve appearance.
2. **Authority at consequential actions.** Trace the selected source version
   and configuration through apply and publication commands. Change code only
   where a reproducible mismatch can target the wrong source or artifact. The
   acceptance test must demonstrate the requested authority and failure behavior.
3. **Workspace maintenance.** Define a reviewable retention policy for preview
   outputs and standalone drafts while preserving referenced runs and reviews.
   Stop at a tested plan before any live pruning.

The readiness decision should report each journey as verified, pending review,
or deferred with a reason. Close blocking defects, record nonblocking work,
and return to the website only after the selected public artifact is reviewed.
Remote security checks and release gardening belong to the subsequent release
phase. More modules or a larger test count are not completion criteria.
