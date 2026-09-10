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
` | `; missing values do not leave empty separators or labels. Section builders
retain field meaning, selection, heading levels, IDs, and tags. Themes control
typography and paragraph spacing.

Education keeps degree, location, and dates together, then gives advisors and
thesis their own paragraphs. Teaching labels optional metrics as `Enrollment`
and `Evaluation`. Publication notes, service descriptions, and other entry prose
remain ordinary paragraphs, with supported inline Markdown formatting preserved.
Avoid joining these blocks with soft line breaks: Pandoc interprets adjacent
lines as one paragraph in HTML, PDF, and DOCX.

`tests/build/test_entry_layout.py` checks actual rendered paragraph boundaries,
optional values, DOCX paragraph structure, PDF labels, and the edited-DOCX
[review round trip](../reference/review-contract.md#markdown-comparison).

An end-only entry date renders its completion year; equal start/end values render
once. A start without an end retains `Present`. Publication titles with a URL
become literal-label HTTP(S) links using the same destination checks as profiles.

Variants may set `section_titles`, for example `experience: Research Experience`
or `skills: Technical Skills`. Keys must name existing semantic sections and
values must be nonempty single-line literal text. These labels change visible
headings only; section order, IDs, tags, and selection remain unchanged. Catalogs
and build manifests record the labels. Content selection belongs in variants;
fonts, rules, alignment, and spacing belong in themes.

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
