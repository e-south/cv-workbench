---
id: howto-publish-site
intent: Prepare and publish native or authored CVs without exposing private contact or reference data.
audience: [operator, agent]
status: active
navigation:
  parent: ../readme.md
---

# Publish a CV

## Native source builds

Keep one private source version and separate contact profiles, for example
`cv-application` with phone and `cv-public` without it. Both can use one theme
and identical content selection. Permit only the public profile in
`publish.yaml` and set `site-sync.yaml`'s `publish_variant` to that profile.

```bash
cvw build --variant cv-public --format md,pdf,docx,ats,html --config <workspace-config>
cvw publication prepare --run <run-directory-printed-by-build> --config <workspace-config>
cvw publication status --config <workspace-config> --json
```

Use the current source and an explicit native run. An older build, changed source,
phone-bearing variant, or mismatched manifest fails before publication writes.
Prepare prints the exact PDF and a local visual packet with a native HTML
reading view when the explicit run includes HTML. To send that view to a site, set `site.cv_html_name: cv.html` in
its sync configuration. Review the HTML and every PDF page, and
check bookmarks, links, typography, and disclosure. If section-rule graphics
changed, visually inspect them before updating the policy fingerprint.

```bash
cvw publication review --pdf-sha256 <reviewed-pdf-sha256> --config <workspace-config>
cvw sync --mode local --config <workspace-config> --site-config <workspace-site-sync>
```

The prepared PDF preserves native text and geometry while removing metadata.
It retains approved HTTPS links declared in selected Markdown and the exact
selected email link. No DOCX, source YAML, build manifest, or phone-bearing file
is sent to the site. `publication status` and the `native.publish` workflow
describe subsequent freshness/review needs. Keep generated outputs disposable;
make later edits in the source, variant, or theme and rebuild both profiles.

## Word-authored CVs

Use this lane when the public artifact must retain the layout of an editable
Word CV. It is distinct from the generated resume lane: the DOCX remains the
editable presentation authority, while structured SoT continues to power
selection and tailored variants.

## Inputs

Keep both inputs outside git:

- the canonical editable `.docx`;
- a PDF exported from that DOCX with the authoring application.

For a header that remains balanced after redaction, align the name, location,
and contact paragraphs to the same body-column edge. Remove manual paragraph
indents and use concise visible labels for profile links. Keep private contacts
at the end of a left-aligned line: PDF redaction removes glyphs without moving
the remaining text. It cannot rebalance a centered or right-aligned line.

Export locally from Word for Mac using **PDF → Best for printing**. The electronic
distribution option uses an online service. Export the whole document, then
check every page before approving a changed visual fingerprint.

Use named paragraph styles and outline levels for section headings in the
editable document. Compare the export after applying styles: Word's contextual
spacing can change when adjacent paragraphs no longer share a style, even if
font settings are unchanged. Preserve the intended spacing explicitly at those
boundaries. Do not infer PDF bookmarks, reading order, or accessibility tags from
the DOCX styles; inspect the exported PDF itself.

The preparation command verifies token-frequency coverage from DOCX to PDF and
from PDF to DOCX, removes fields and sections prohibited by
`config/publish.yaml`, strips hidden or embedded payloads, rejects hidden or
non-HTTPS links, rejects raster or complex vector content that cannot be
verified against the text policy, and validates the result before replacing
`var/publish/<variant>/cv.pdf`. The manifest records content hashes and the
transformation without publishing local paths.

Disclosure checks also inspect bookmark titles and accessibility strings. Private
values in those fields stop preparation rather than being silently rewritten;
see [non-page disclosure](../reference/publication-contract.md#non-page-disclosure).

`config/publish.yaml` also pins `approved_visual_fingerprint_sha256`. When an
authored export changes its non-text rectangle layout, preparation reports the
observed fingerprint and stops. Compare the new export visually with the DOCX;
only after that review should you update the approved fingerprint and rerun.
This keeps table rules and underlines possible without treating arbitrary
rectangle or horizontal-rule compositions as automatically safe. Text-only redactions use a
transparent overlay and the saved public PDF must retain the source rectangle
fingerprint exactly.

## Prepare

```bash
uv run cvw prepare-public-pdf \
  --authored-source /private/path/to/cv.docx \
  --source-pdf /private/path/to/exported-cv.pdf \
  --plain
```

Preparation prints a `review` path under
`var/reviews/publication/<pdf-sha256>/review.html`. Open that local file to review
all pages, or serve only that directory on loopback with `uv run python -m http.server
--bind 127.0.0.1 --directory <review-directory> 4401`.

The packet contains the exact sanitized PDF, 96-DPI page previews, and
`review.json` with the PDF hash, page dimensions, text bounds, and link counts.
It contains no private source paths or source metadata. Rendering is bounded to
50 pages and 40 million pixels across the document; larger artifacts fail
before replacing publication outputs.

Check header alignment after contact removal, readable link labels, line wraps,
page breaks, table rules, and unexpected blank pages. A successful preparation
proves the disclosure and fidelity contracts; it does not approve aesthetics.
The ordinary `preview` command renders the generated-resume lane and cannot
validate the authored public CV.

Inspect freshness and record review of the exact hash printed by preparation:

```bash
uv run cvw publication status --json
uv run cvw publication review --pdf-sha256 <reviewed-pdf-sha256>
```

The private preparation record retains the explicit source pair and detects
later source/export/configuration changes. Review binds to this preparation and
the exact PDF; changed or damaged artifacts require preparation and review
again. No command records review merely because a packet exists. Publication
selection defaults to `site.publish_variant`, independently of generated builds.
Inspect `uv run cvw workflow --id authored.publish` for the current sequence.

After recording review, sync only the validated PDF and sanitized manifest:

```bash
uv run cvw sync --mode local --plain
```

## Failure Policy

Preparation and sync fail closed when the source pair is unrelated, the PDF is
invalid or encrypted, embedded files are present, a forbidden phone or section
survives, an unauthorized email or hidden link appears, provenance or policy
metadata disagrees, a destination escapes the configured site repository, the
PDF contains unverifiable raster, annotation, form, or complex-vector data, or
any removed character falls outside an exact policy-derived redaction region,
or any surviving character changes its page, order, origin, bounding box, font,
size, style flags, or color, or any approved vector graphic changes. Phone
policy covers recognized third-party phone shapes as well as the owner's Source
of Truth value and removes an adjacent separator with the contact. Section
removal starts at the exact heading line, not an earlier prose mention, and a
forbidden section must be terminal so it cannot consume a later allowed
section. Do not replace this lane with a Markdown-to-PDF rebuild when layout
fidelity is the requirement.

Retained links must exactly match a public link in the person Source of Truth,
use HTTPS, and have a click rectangle that closely matches visible label text.
Valid link rectangles are tightened to their visible labels before redaction so
a small annotation overlap cannot erase a link beside a private contact line.
Preparation stages the PDF and provenance manifest together and restores the
prior pair if either replacement fails.

Continue with [the publication lifecycle](../reference/publication-contract.md)
for freshness states and private records, and [the site contract](../reference/site-contract.md) for ownership
and write-boundary details, then [security](../reference/security.md) for the
public disclosure policy.
