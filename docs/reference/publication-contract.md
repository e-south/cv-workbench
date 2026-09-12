---
id: reference-publication-contract
intent: Define native and authored publication provenance, freshness, and recorded review before site handoff.
audience: [operator, agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Publication Lifecycle

Native source builds use `publication prepare --run <explicit-run-directory>`.
Word-authored CVs use `prepare-public-pdf` with an explicit DOCX/PDF pair.
Both paths produce a checked PDF, private preparation record, visual packet,
and hash-bound review receipt before the same site sync boundary.

## Native build publication

`native_inputs.py::capture_native_build` requires a run beneath configured
`paths.runs`, containing Markdown, PDF, and a build manifest. It checks output
hashes, source/snippet hashes, variant identity and hash, and workbench settings
against current inputs. It never selects a run by timestamp or filename.
The public variant must exclude forbidden contact fields and sections before
rendering. Application and public variants can share one source and theme.

`native.py::prepare_native_public_pdf` captures those bytes, checks disclosure
and link eligibility, removes metadata, and proves that sanitization preserves
every glyph and graphic. Standard PDF creation/modification timestamps are
removed before phone-pattern checks; other metadata, page text, and non-page
strings remain subject to disclosure checks. Native publication does not redact
visible contact data or reflow a phone-bearing document into a public version.

Native link eligibility comes from Pandoc-parsed links in the selected,
hash-verified Markdown. Only absolute HTTPS URLs without credentials and the
selected person's exact email `mailto:` target are eligible. PDF annotations
cannot supply their own allowlist. Every click area must match visible glyphs;
unlinked adjacent punctuation is excluded from label geometry.

The `native-pdf-publication` manifest records native run, Markdown and PDF hashes,
the approved graphics fingerprint, link targets, and `native-sanitization` with
zero redactions. It does not assert Word authorship. `NativePreparationRecord`
owns all private input paths and source-file stamps. Input changes during
preparation reject replacement; later changes invalidate review. Adding source
files or changing active source selection also requires rebuilding/preparing.

The `native.publish` recipe appears for recorded native preparations. Status,
review, and sync verify native provenance against current inputs, including the
Markdown link declarations. Only the PDF, optional prepared reading HTML, and smaller sanitized site manifest
cross the site boundary; source manifests, link attestations, and private
preparation/receipt files do not. See `tests/ops/publication/test_native.py` and
the [publication guide](../howto/publish-site.md#native-source-builds).

## Native HTML reading view

When the explicit native run includes HTML, preparation captures that completed
output and its manifest-hashed CSS. It never reconverts intermediate Markdown:
contact rows, entry projections, typography, and spacing come from the same
rendering path as the workbench preview. A PDF-only run has no reading view.

`reading.py` preserves native heading/list structure, layout classes, scientific
emphasis, and approved HTTPS/email links. It strips unrelated attributes and
head metadata, rejects active/embedded content and network-dependent CSS, and
applies the shared contact/section disclosure checks to text and styles. The
result is a self-contained UTF-8 HTML document with its captured theme.

The optional `reading_html` descriptor records its filename and SHA-256 separately
from the primary PDF output. Preparation stores identical HTML in the review
packet; review and sync bind its hash to the preparation receipt. Changing the
native HTML, its stylesheet, or the prepared document invalidates review.

A site opts in through `site.cv_html` and receives reviewed HTML plus its
sanitized path/hash. The consumer may scope that completed theme within its page;
it must not reconstruct entry layout or compile Markdown. Inspect both native
HTML and PDF before recording review. This does not add PDF structure tags or
establish PDF/UA conformance. Authored DOCX/PDF preparation does not infer HTML.

## Authored source pair

The editable DOCX and its authoring-app PDF export are explicit inputs to
`prepare-public-pdf`. Generated resume builds do not update this source pair.
Publication commands default to `site.publish_variant` in `site-sync.yaml`,
independently of the default generated-document variant. Pass `--variant` to
select another declared publication explicitly; missing selection is surfaced
without guessing from build output.
The source correspondence check is a token-coverage check; it does not prove
that an export was made after every edit or has identical wording and order.

## Input lifetime

Preparation and sync each capture one workbench configuration before resolving
their settings. Both Python APIs accept a path or `ConfigSnapshot`; preparation
and sync CLI selection passes that same snapshot into the operation. An edit or
removal of `workbench.yaml` after capture does not redirect its output, review,
or source settings. A later path-based invocation reads current settings.
The [configuration contract](configuration-contract.md) owns snapshot semantics.

`inputs.py::capture_publication_inputs` reads the authored DOCX, exported PDF,
policy, variant, and person file into private temporary copies. Source
correspondence, redaction, disclosure, and layout checks process those captured
bytes. Per-role directories prevent equal filenames from colliding. The temporary
directory has mode `0700` and input copies have mode `0600`; normal completion,
errors, and cancellation remove this operation's copies.

`record.py::PreparationInputs` records the original resolved file paths and
hashes of those captured bytes. `preparation_bytes` verifies that all five
original files still match before serializing provenance. Missing or changed
inputs reject preparation before replacing the prepared PDF, manifest, private
record, or packet. An unrelated exported PDF cannot inherit the correspondence
result from an earlier source pair. Temporary paths never become source identities
in preparation records or authored manifests.

The configuration snapshot covers workbench settings. Input capture is per file,
not a simultaneous snapshot of every source or a lock on other applications.
Changes after the final freshness check can make a completed preparation stale;
status/review/sync must still inspect current inputs. Capture and cleanup are not
crash-durability guarantees. Sync retains its separate captured-PDF copy plan,
policy validation, and exact-review gates; capturing workbench settings does not
claim a single snapshot across every sync input.

`tests/ops/publication/test_authority.py` exercises API/CLI configuration edits
and removal, input changes during preparation, unchanged existing outputs on
rejection, private-copy permissions, cancellation cleanup, and original provenance.

## Private preparation record

Preparation atomically writes `preparation.json` beside the prepared PDF and
manifest under the configured publish directory. This private record stores
the selected input paths and hashes, the publication policy, variant and person
hashes, the public PDF and manifest hashes, and the visual packet file hashes.
It is a snapshot of the inputs used for this preparation, not another editable
CV or a replacement for the authored source. It never crosses the site boundary.
Preparation and review records are written with owner-only permissions (`0600`).

`publication status` and the `context` publication section inspect current bytes.
They report unconfigured, untracked, missing, stale_source, stale_export,
stale_configuration, invalid, review_required, or reviewed. Reasons identify the
specific failed contract. Missing provenance is never inferred from filenames,
timestamps, the latest generated build, or the existence of a review directory.

## Review receipt

After inspecting the exact public PDF and page packet, the caller records review:

```bash
cvw publication review --pdf-sha256 <hash-shown-in-review-packet>
cvw publication status --json
```

The command checks current source, policy, artifact and packet integrity before
writing a private `review-receipt.json`. The receipt binds the caller's review
declaration to the PDF hash and preparation-record hash. It records a timestamp;
it is not proof that a human read the document. A changed preparation or damaged
packet requires review again. Repeating an identical preparation preserves a
still-current receipt.

The static packet identifies itself as review evidence, not live lifecycle
status. Its content stays fixed after review is recorded; `publication status`
owns the current freshness and review verdict.

## Handoff

Sync requires current inputs and a matching receipt in addition to the existing
disclosure, fidelity, manifest and destination checks. It fails before any site
write when preparation is stale, missing or unreviewed. A reviewed state means
the local artifact is eligible for the sync checks; it does not claim that the
site has already been updated. Only the PDF, optional prepared reading HTML, and sanitized site manifest cross
that boundary.

Older prepared artifacts without a preparation record must be prepared again
with explicit source paths, reviewed, and then synced. There is no inferred
migration or automatic approval. See [the authored CV guide](../howto/publish-site.md)
for the operator journey and [the site contract](site-contract.md) for writes.

## Non-page disclosure

The same phone, email, and forbidden-section checks apply to page text and
decoded PDF object strings. Bookmark titles, accessibility descriptions, text
alternatives, and nested or indirect string values can retain private content
after visible glyphs have been removed. Preparation and captured-byte sync
validation both inspect these values before publishing an artifact.

`ops/publication/object_text.py::pdf_object_text` uses MuPDF to parse dictionaries
and arrays and decode PDF string encodings. It visits cross-reference objects
without following indirect edges, avoiding cycles through page parents and
structure trees. Unreadable object text fails closed. Opaque stream bytes are
outside this string inspection; attachment, visual-payload, and link checks
retain their separate responsibilities. This is not a general malware scanner.

Public bookmarks and accessibility descriptions remain intact when they satisfy
the disclosure policy. Bookmarks may navigate within the document or group other
bookmarks. Named destinations must resolve to a page in the same PDF;
external, unsupported, or chained bookmark actions are rejected. Both
the resolved destination and underlying action dictionary are checked, because
the summary can omit JavaScript or a subsequent action. Page links still require the
approved visible-label and exact-target checks.

Preparation does not guess how to rewrite accessibility text after redaction.
If private object strings remain, it stops before replacing publication files.
Correct the authored public content and export again, then repeat preparation
and review. The existing prepared artifact is preserved on rejection. These
checks neither add structure tags nor establish accessibility conformance.
See `tests/ops/publication/test_object_text.py` for retained public structure,
hidden-contact rejection, encoding/indirection cases, and output preservation.

## Code ownership

`ops/publication/` owns the lifecycle: `record.py` defines the private schemas,
`state.py` inspects freshness and records review, `pdf.py` performs sanitization,
`inputs.py` owns captured preparation copies,
`object_text.py` decodes non-page strings, `packet.py` renders review evidence,
`policy.py` loads disclosure policy, and
`manifest.py` defines and serializes authored provenance, and `artifact.py`
validates manifest eligibility. Python consumers use these modules;
the former flat `ops/public_pdf.py`, `ops/publish.py`, and
`ops/publication_review.py` paths have moved. CLI spellings for preparation and
sync remain unchanged. `cli/commands/publication.py` owns their adapters plus the
`publication status` and `publication review` commands; `workspace/publication.py`
owns the workflow description. Site writes remain in `ops/syncing.py`.

Approved graphics may contain rectangles and horizontal section rules, pinned
by their exact geometry/style fingerprint. Curves, diagonal paths, rasters,
widgets, and unsupported annotations remain rejected. The fingerprint is a
review declaration about non-text graphics, not a proof of document aesthetics.

## Authored provenance schema

Preparation and artifact validation share `manifest.py::PublicationManifest`.
The authored manifest requires an explicit integer `schema_version: 1`, the
`authored-pdf-publication` kind, exactly one PDF output, the selected variant's
selection fields, complete authored/exported source names and SHA-256 hashes,
visual fingerprint, coverage measurements, and semantic-redaction policy/count.
Source names are filenames, not paths. Coverage must be finite and within
`[0, 1]`; redaction count must be a nonnegative integer. Unknown fields and
duplicate JSON keys are rejected. Booleans cannot stand in for integers, and
string-valued numbers are rejected. Schema errors report field locations
without echoing the invalid values.

This provenance is separate from the smaller sanitized site manifest defined
by the [site contract](site-contract.md). The private preparation record owns
source paths, freshness, and review dependencies. Valid provenance or a coverage
score does not establish human review or prove exact source wording/order.

`artifact.py::read_public_artifact` captures immutable PDF bytes and verifies
their signature/hash against the manifest and variant/policy declarations.
`pdf.py::validate_public_pdf_content` inspects those same bytes for forbidden
content, unsafe links, encryption, attachments, and unapproved graphics. Sync
requires both checks and binds the captured hash to the current reviewed
publication before constructing its copy plan.
