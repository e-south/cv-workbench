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

The HTML output is written to `var/dist/<variant>/cv.html`. The command prints
the local preview URL; use Chrome DevTools MCP to open and interact with it.

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
