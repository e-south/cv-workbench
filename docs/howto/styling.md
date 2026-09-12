---
id: howto-styling
intent: Explain theme, format, and style-preset ownership.
audience: [operator, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Styling and themes

cv-workbench styles outputs through theme packs. A theme is a directory under
`build/themes/` with a `theme.yaml` plus Pandoc defaults and optional style
presets. Themes keep layout and typography separate from SoT content and
variants.

## List available themes

```bash
uv run cvw theme list
```

Shipped themes currently include `default`, `editorial`, and `signal`.

## Inspect a theme

```bash
uv run cvw theme info default
uv run cvw theme info editorial
```

## Render with a theme and preset

```bash
uv run cvw build --sot-path ./sot.sample --variant base --theme default --style-preset modern
uv run cvw build --sot-path ./sot.sample --variant base --theme default --style-preset compact
uv run cvw build --sot-path ./sot.sample --variant base --theme editorial --style-preset modern
uv run cvw build --sot-path ./sot.sample --variant base --theme signal --style-preset compact
```

## Quick HTML preview

```bash
uv run cvw preview --sot-path ./sot.sample --variant base
```

The live preview auto-rebuilds on SoT/theme changes and exposes a left sidebar
with fast controls (HTML + PDF auto-build by default):

- `t`: cycle theme
- `p`: cycle style preset
- `v`: cycle variant
- `f`: cycle format
- `r`: rebuild with current settings
- `x`: stop the preview server

Closing the browser tab does not stop the preview server. Use the Stop button
or run:

```bash
uv run cvw dev stop
```

The command prints the local preview URL and rendered HTML path. Files live in
an [invocation-scoped preview directory](../reference/preview-contract.md#artifact-ownership),
separate from audited build output. Use Chrome DevTools MCP to open and interact
with the local URL.

## Theme layout

```
build/themes/<theme>/
  theme.yaml
  pandoc/
    common.defaults.yaml
    pdf.defaults.yaml
    html.defaults.yaml
    docx.defaults.yaml
  styles/
    pdf/
      modern.tex
    html/
      modern.css
```

### Defaults files

Pandoc defaults files declare writer settings and metadata for a route. Keep
these small and focused so they can be composed cleanly.

### Style presets

Style presets live under `styles/pdf/` and `styles/html/` and are referenced by
`--style-preset`. For PDF, presets are included via `--include-in-header`. For
HTML, presets are attached via `--css`.

Presets are the preferred way to tweak presentation without creating new
variants. Keep variants focused on content selection.

### DOCX styles

A DOCX route may declare `reference_doc: reference.docx` in `theme.yaml`.
The file must exist inside that theme directory; absolute paths, escapes through
symlinks, and declarations on other format routes fail during planning. Use a
neutral reference document containing styles and page settings, without personal
content. Pandoc applies it during rendering, so changes belong in the theme
rather than in generated DOCX archives. Its bytes join the theme fingerprint and
the build's render-asset checks. `tests/build/test_docx_reference.py` verifies
actual DOCX styles and rejects changed assets before output writes.

Rendered DOCX packages must contain core document parts and well-formed XML
before replacing an existing artifact. A successful Pandoc exit alone is
insufficient: malformed styles or relationship XML fail the render and preserve
the prior output. This checks package structure, not desktop pagination or every
Office schema rule. When editing reference XML, preserve conventional namespace
prefixes; older Pandoc versions can mishandle renamed prefixes when adding styles.

### Optional compact presentation

Set these Boolean values under `metadata` in a theme's Pandoc defaults:

```yaml
metadata:
  cvw-compact-entries: true
  cvw-contact-rows: true
```

The bundled `presentation.lua` filter is otherwise a no-op. Compact entries join
an entry's third-level heading and first metadata paragraph, making the heading
bold while retaining its identifier and attributes. Simple education highlights
join that paragraph with semicolons; other narrative paragraphs remain separate.
Self-author names become bold without losing their spans or link targets.

Contact rows split the first contact paragraph after its second link, when at
least three links exist. Select email followed by the primary website for a
balanced first row. All text and links are retained, with later profiles on the
second row. HTML themes style `.contact-block`; DOCX reference documents may
define a `Contact` paragraph style. PDF rows are centered. This presentation does
not add icons, text boxes, or document headers.

Verification: `tests/build/test_compact_presentation.py` checks unchanged default
structure, preserved identifiers/attributes, links, wording, and contact rows.

## Template guidance

The default theme uses Pandoc's built-in templates (`template: default`). If you
want full control, add a template file and point to it from `theme.yaml`.

## Contact presentation

Generated resumes and cover letters share `build/contacts.py` for their contact
line. The variant's `contact_fields` selects which facts are shown; themes own
their visual styling. Profile labels such as `GitHub` or `Research` become
clickable text instead of displaying the full URL. Email remains visible as an
address with a `mailto:` destination. Markdown, HTML, PDF, and DOCX preserve
these links through Pandoc. Phone and location remain plain text.

Keep a concise, meaningful `label` beside each `person.links[].url`. Contact
labels and other contact text are literal text, with Markdown punctuation
escaped so it cannot introduce formatting or additional links. Internal label
whitespace is collapsed to keep the header in one paragraph.

Selected profile destinations must be absolute HTTP(S) URLs without credentials,
control characters, whitespace, or backslashes, with a hostname and valid port.
Selected email values must be bare addresses, not `mailto:` strings with URI
headers. URI punctuation is encoded where needed. These checks run during build
planning, before artifact writes; errors identify the contact field or profile
index without echoing its value. Excluded fields are neither emitted nor turned
into link destinations. This is a rendering contract, not address-deliverability
or remote-site verification. Source validation retains its existing schema.

The authored-CV lane keeps its links in the Word source and follows the stricter
[public PDF policy](../reference/publication-contract.md); generated contact
links do not approve an artifact for publication.

Verification: `tests/build/test_contacts.py` inspects actual HTML anchors, PDF
annotations, and DOCX relationships for both document types, plus preflight
failure, literal-label, and contact-selection behavior.


## Entry structure

Education, publication, conference, honor, service, teaching, and reference
entries use `build/entry_layout.py` to emit a compact metadata paragraph followed
by separate narrative paragraphs. Nonempty metadata values are separated by
` | `, except publication citations; missing values do not leave empty separators or labels. Section builders
retain field meaning, selection, heading levels, IDs, and tags. Themes control
typography and paragraph spacing.

Publication citations use sentence punctuation between authors, venue details,
and any required status. Journal details render as `Journal (year), volume(issue): pages`;
absent fields leave no empty punctuation. The native source owns citation order
and journal names, including any preferred standard abbreviations. Authorship
roles, DOI links, and preparation status survive this presentation change.
`tests/build/test_publication_status.py` verifies citation punctuation and missing
metadata; `tests/build/test_concise_entries.py` checks inline contribution notes.

Education keeps degree, location, and dates as distinct semantic spans, then gives advisors and
thesis their own paragraphs. Teaching labels optional metrics as `Enrollment`
and `Evaluation`. Publication notes, service descriptions, and other entry prose
remain ordinary paragraphs, with supported inline Markdown formatting preserved.
Avoid joining these blocks with soft line breaks: Pandoc interprets adjacent
lines as one paragraph in HTML, PDF, and DOCX.

`tests/build/test_entry_layout.py` checks actual rendered paragraph boundaries,
optional values, DOCX paragraph structure, PDF labels, and the edited-DOCX
[review round trip](../reference/review-contract.md#markdown-comparison).

Equal start/end values render once; ISO year-month values render as English month
and year. Education labels a start-only date `Started`; an end date alone does
not assert graduation. Other ongoing entries retain `Present`. Publication titles with a URL
become literal-label HTTP(S) links using the same destination checks as profiles.
Optional publication `title_italics` lists exact phrases to italicize in the title,
including within its link. Keep `title` as ordinary citation text. Source validation
rejects missing, repeated, or overlapping phrases; the renderer escapes all other
markup. Use ordinary Markdown emphasis in authored narrative paragraphs.

Variants may set `section_titles`, for example `experience: Research Experience`
or `skills: Technical Skills`. Keys must name existing semantic sections and
values must be nonempty single-line literal text. These labels change visible
headings only; section order, IDs, tags, and selection remain unchanged. Catalogs
and build manifests record the labels. Content selection belongs in variants;
fonts, rules, alignment, and spacing belong in themes.

Adjacent rendered sections with the same explicit `section_titles` value share
one visible heading. Their records keep their source IDs, selection, and order.
Use this to present service and conference records together without moving
conference facts into the service collection. An intervening visible section
starts a new heading, even if a later section repeats the same title.

### Referenced record layout

Use `variant.render.entry_layout` when one document should place recognition
beside a related role or group short activities. References use selected record
IDs from `canonical.md`; section targets use Pandoc heading IDs.

```yaml
variant:
  render:
    entry_layout:
      - sources: [honor-research-award]
        target: role-researcher
        placement: details
        fields: [heading]
      - sources: [service-rotations, service-project-team]
        target: teaching-mentoring
        placement: section
        label: Research mentoring
        fields: [summary, date]
```

`details` appends to a role or degree's semantic detail line. `section` creates
one native bullet at the first source's position when it belongs to that section,
or at the destination section's end otherwise. Labels are literal text. Each
consumed record keeps its ID on a span; unrelated prose remains in place, and
empty sections disappear. There are no layout tables or copied source records.

By default, simple service, honor, and conference records retain all metadata
and their summary. Optional `fields` chooses and orders `heading`, `role`,
`issuer`, `location`, `detail`, `date`, or `summary` for this presentation only.
Use it to avoid repeating a role or organization already clear from context;
review responsibility, scope, recognition, and attribution after any omission.
Requested fields must exist, except unknown dates remain absent. A neighboring
record never supplies a missing date. Unsupported body structure, duplicate or
missing references, and targets consumed by another rule fail rendering.

For a standalone `section` projection, set `date_position: right` to use the
same date alignment as ordinary entries, without parentheses. It requires one
source with a known date; explicit `fields` must include `date`. Grouped entries
retain dates in parentheses beside each source so a year cannot be mistaken for
the whole group's date. The aligned-entry theme supplies the shared HTML row,
PDF alignment, and native DOCX `Entry Heading` tab stop.

For multiple manuscripts with identical authors, year, and preparation status,
use `placement: shared_citation` with their publication IDs and the Publications
section ID. Their source records remain separate. The render shows one citation
followed by all titles as bullets, preserving title links and record IDs. This
requires complete authorship/year, matching citation structure, explicit
`in_preparation` status, and no extra notes. It rejects differing metadata and
cannot omit fields or supply a replacement label. Published papers remain
individual citations.

Conference records may declare a `series` separately from their meeting `event`.
The canonical heading retains both; `title` remains the presentation title and
must not substitute for the meeting topic. A `section` rule with `group_by: series`
shows contiguous records under one shared conference-family label, retaining
each topic, date, and source ID. For example:

```yaml
conferences:
  - id: cells
    series: Research Conferences
    event: Cell Biology
    year: 2025
  - id: stress
    series: Research Conferences
    event: Stress Responses
    year: 2024
```

Use `fields: [heading, date]` with the conference references and a label such as
`Posters`. Records without a series remain independent items. Topic headings
cannot be omitted, right-aligned dates cannot be combined with series grouping,
and repeated series must be contiguous in the explicitly selected source order.
Grouping is a presentation choice; do not combine unrelated service roles merely
to save a bullet or turn award-recipient language into an action claim.

The native `entry_projection.lua` filter runs before theme presentation. All
rendered formats use the same projection; `canonical.md`, `resume.json`, source
selection, and source files retain the original records. Variant catalogs and
manifests record the layout rules. DOCX review of a changed presentation remains
a review diff, without manufacturing source edits from regrouped text.

Groups use `.entry-group.cv-entry` and the same PDF `\cvwentryspace` hook as
ordinary records when entry structure is enabled. Keep responsive date stacking
scoped to `.entry-heading .entry-date` so dates inside grouped text stay inline.
Check actual PDF/DOCX wrapping: consolidation does not guarantee fewer lines.

With entry structure enabled, compacted records retain bold identifying labels:
the role when present, otherwise the heading. A supplied group label provides
the emphasis instead, and metadata attached to another record stays regular.
Shared manuscript titles retain the same emphasis as individual publication
titles. Projection marks these identities with `.entry-label`; the shared
structure filter applies emphasis across HTML, PDF, and DOCX. Dates and summaries
are not promoted to labels, and source wording is unchanged.

Verification: `tests/build/test_entry_projection.py` exercises native writers,
source and review retention, literal metadata labels, and invalid references.

### Deliberate page starts

Set `variant.render.page_break_before` to a list of Pandoc heading IDs for a
specific document, for example:

```yaml
variant:
  render:
    page_break_before: [education]
```

This optional rendering choice is recorded in the variant catalog and build
manifest. It does not change another variant using the same theme. PDF inserts
a page break, DOCX inserts a native page break, and HTML uses `break-before:
page` for printing while retaining continuous screen flow. Ordinary text and
source records retain their reading order. Heading IDs start with an ASCII
letter and contain only letters, digits, dots, underscores, or hyphens.
Duplicate, missing, or ambiguous targets fail rendering.
Renaming a heading can change its automatically generated ID, so update this
setting and verify pagination when changing section labels.

The underlying `page_breaks.lua` filter also accepts a theme metadata list named
`cvw-page-break-before`. Reserve theme-wide settings for layouts whose headings
are shared by every consuming variant. A break fixes a section start; it cannot
guarantee earlier content fits on one page. Check the actual PDF after edits.

### Aligned entry dates

Set `metadata.cvw-aligned-entries: true` in a theme's common Pandoc defaults to
place an entry's institution or organization and location on the left, with its
date on the right. Role/degree and narrative stay on separate lines. Conference
entries lead with the event, followed by presentation type and title. The opt-in
filter uses `entry-detail`, `entry-location`, and `entry-date` spans emitted by
the shared metadata helper; it does not parse display strings. Unknown metadata
is left intact. IDs, links, and selected content survive the transformation.

HTML themes style `.entry-heading > p`, `.entry-identity`, and `.entry-date`.
Use a flex row with a minimum gap, and stack the date at narrow widths. PDF uses
native TeX spacing with a minimum gap and keeps the heading with its next block.
The DOCX theme must provide an `Entry Heading` paragraph style with a right tab
stop at the text-area boundary and `keepNext`; no layout table is inserted.
Keep OOXML namespace prefixes intact when editing a reference DOCX.
For PDF entry spacing, a theme may define `\cvwentryspace`, for example
`\newcommand{\cvwentryspace}{\addvspace{5pt}}`. The aligned renderer calls it
before each entry heading. An undefined hook adds no spacing. Match this rhythm
with HTML entry margins and the DOCX `Entry Heading` style, rather than inserting
blank source paragraphs. Name alignment belongs to each theme's top-level heading
style; contact alignment is independent.

With concise entries enabled, education paragraphs are grouped in
`.education-details`, using the DOCX `Education Details` paragraph style.
This keeps degree, advisor, and thesis paragraphs available for separate styling.
To remove extra paragraph space within each degree while preserving entry gaps,
style `.education-details p` in HTML, set paragraph spacing in `Education Details`
for DOCX, and define `\cvweducationdetails` in the PDF theme (for example,
`\newcommand{\cvweducationdetails}{\setlength{\parskip}{0pt}}`). The PDF hook is
scoped to the education details; it does not alter subsequent paragraphs. An
undefined hook preserves the surrounding theme's paragraph spacing.

This option takes precedence over `cvw-compact-entries` for semantic entries;
unaligned legacy entries retain the existing compact behavior. Disable compact
entries when publication titles and full author lists need separate paragraphs.
The candidate's author span remains emphasized with either presentation option.
The text export retains ordinary linear metadata. Validate actual PDF wrapping,
DOCX tab/style structure, and HTML responsiveness after enabling the option.

After editing packaged filters in a checkout, run
`uv sync --reinstall-package cv-workbench` before native builds. Python's editable
installation does not automatically refresh the wheel's copied filter resources;
the build manifest records the filter hashes actually used.

### Concise entry details

Set `metadata.cvw-concise-entries: true` alongside aligned entries to place a
service or conference role before its organization/event and an award issuer after its title on the
identity line. The shared metadata helper emits `entry-role` and `entry-issuer`
spans; presentation uses those roles rather than parsing names or display text.
Dates keep the existing right-alignment and narrow-view stacking behavior.
Substantive descriptions remain separate paragraphs. Missing or duplicated
metadata does not justify dropping text; ambiguous entries are left intact.

With this option, simple Education highlights join the degree line with
semicolons; advisors and thesis remain separate. Nested or multi-paragraph
highlights keep their list structure. Publication notes marked
`entry-note` join the preceding citation or status paragraph, preserving working-title
qualifications or contribution explanations without adding a paragraph.
When authors are present, their `entry-authors` span keeps the note beside the
author list, before the venue details. Its source may use ordinary Markdown
emphasis, for example a bold authorship contribution note.
The note compaction also works without aligned dates. These are presentation
changes: canonical source records, IDs, selection, and ordinary text exports
retain their fields. With the option disabled, existing detail lines remain.

Keep factual restoration and removal of redundant prose in the source version;
the filter never decides which assertions are dispensable. Verify native output
with `tests/build/test_concise_entries.py`, including unknown presentation titles,
optional dates, ambiguous metadata, and actual PDF/DOCX/text builds.

### Repeated teaching and publication labels

The canonical teaching renderer groups adjacent selected records with exactly
matching course and role under one heading. Every offering keeps its source ID,
term, enrollment, evaluation, and summary. Selection happens first; different
roles or nonadjacent courses remain separate. This structure also reaches plain
text without a layout table. Source records and machine-readable exports retain
the individual offerings.

Set theme metadata `cvw-inline-teaching: true` to present adjacent offerings on
one evidence paragraph under their shared course/role heading. Each term keeps
its own ID, enrollment, and evaluation; displayed terms use parentheses, while
the source still has separate records. Compact section projections also use
parenthesized dates and unspaced en dashes for ranges. A projection explicitly
configured with `date_position: right` retains the aligned date presentation.
If any offering has narrative or unsupported block content, the whole group
keeps its expanded layout. With teaching bullets enabled, an inline group uses
one native bullet for the course and its evidence. Inspect wrapping at the
selected font size; a single paragraph is not a promise of a single line.
As with other aligned layouts, DOCX import can produce a review-only diff; apply
content changes through native source unless the importer explicitly supplies
an applyable patch.

### Justified prose lists

Themes can set `cvw-justify-lists: [skills, experience]` to style prose lists
independently of heading/date rows. These are the supported section keys; unknown
values fail instead of broadening alignment. Skills have a semantic `skills-list`
container, so styling does not depend on the displayed section title or a person's
record ID. Experience alignment applies only to its `entry-items` bodies.

`body_alignment.lua` supplies `body-justified`, the optional LaTeX hook
`\cvwjustifiedlist`, and Word styles `Justified List` / `Justified Entry Bullet`.
The theme owns justification, hyphenation, paragraph rhythm, and list insets. Base
the Word styles on the existing list styles with `<w:jc w:val="both"/>`; avoid changing
the heading style. For LaTeX, a local alignment macro can change list alignment
without resetting the existing `enumitem` geometry. In HTML, keep the final line
left aligned and consider a left-aligned fallback on narrow screens. Inspect real
wrapping and word spacing; justification alone cannot guarantee no short last line.

An explicitly published paper with a journal/venue omits the redundant
`Published` display label. Without a venue the label remains; manuscripts in
preparation always keep their status. Source status is unchanged. Authoring a
contribution note within a publication lets concise presentation place it beside
that citation. Notes are never removed automatically based on their wording.

## Build-time changes and provenance

Finish theme/style edits before starting a build. If a recorded asset changes
while rendering, the build reports the changed path and preserves the previous
bundle; rebuild after the edits settle. A live preview keeps its last successful
output and reports the error through its usual status surface.

The [render-asset contract](../reference/configuration-contract.md#render-asset-lifetime)
defines tracked files, filter fingerprints, and concurrency limits. Templates
and defaults retain their existing path resolution; this check does not package
or freeze their indirect dependencies. PDF engine metadata follows the selected
theme route. Other formats do not require probing a PDF engine.

### Shared entry rhythm and activity lists

Set `metadata.cvw-entry-structure: true` alongside aligned entries to apply one
entry/detail structure across Education, Experience, Publications, Projects,
Teaching, Service, Conferences, and Honors. The separate `entry_structure.lua`
filter runs after presentation and is included in the build's filter hashes.
It preserves source IDs, wording, links, and ordering. Existing themes that do
not opt in retain their previous structure and Education-specific hook.

The shared structure provides `.cv-entry`, `.entry-kind-<kind>`, `.entry-heading`,
and `.entry-details`; DOCX paragraphs use `Entry Heading` and `Entry Details`.
PDF invokes `\cvwentryspace` before records and scopes `\cvwentrydetails` to the
details. Undefined hooks leave the theme's defaults in place. With this option,
these generic hooks replace the Education-specific details hook.

Keep the numeric settings in the theme. For example, define `\cvwentrygap` once,
use it in `\cvwentryspace`, and reuse it as `enumitem`'s `itemsep` for skills lists.
Use a matching CSS custom property for `.cv-entry` margins and `li + li` spacing.
Set DOCX paragraph spacing in the reference styles; never insert empty source
paragraphs to tune layout.

Lists inside entry details or composed entry groups expose `.entry-items` and
the scoped PDF hook `\cvwentryitems`. Use these for a smaller within-record gap
while retaining separation between records and skill categories. DOCX uses
the `Entry Bullet` paragraph style for these native list items; define it in
the theme's reference document. This style is independent of `Compact`, which
continues to control ordinary lists. Source bullets and reading order remain
unchanged, and undefined PDF hooks retain the theme's list defaults.

To add semantic bullets and hanging indentation to selected record kinds:

```yaml
metadata:
  cvw-entry-structure: true
  cvw-bulleted-entries: [service, honors, conferences, teaching]
```

The allowed kinds are `education`, `experience`, `publications`, `projects`,
`teaching`, `service`, `conferences`, and `honors`. The value must be a YAML list;
unknown kinds fail instead of silently ignoring a typo. Grouped teaching keeps
one course heading and lists its individual terms. Narrative remains a paragraph
within each activity, while nested source lists retain their hierarchy. Bullets
are native lists in HTML, PDF, and DOCX, not manually inserted glyphs. Verify the
reference DOCX's list indentation and right date tab against the text area, and
inspect actual wrapping at the selected font size.

For a short label that must not split, use `[label text]{.keep-together}` with
entry structure enabled. HTML uses `white-space: nowrap`, PDF uses a TeX box,
and DOCX uses nonbreaking spaces and native nonbreaking hyphens. The ordinary
source text stays readable in text exports. Reserve this for labels shorter
than the available line; it cannot make an overlong phrase fit a narrow column.
