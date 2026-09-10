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
