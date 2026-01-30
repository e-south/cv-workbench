# Styling and themes

cv-workbench styles outputs through theme packs. A theme is a directory under
`build/themes/` with a `theme.yaml` plus Pandoc defaults and optional style
presets. Themes keep layout and typography separate from SoT content and
variants.

## List available themes

```bash
uv run cvw theme list
```

## Inspect a theme

```bash
uv run cvw theme info default
```

## Render with a theme and preset

```bash
uv run cvw build --sot-path ./sot.sample --variant base --theme default --style-preset modern
uv run cvw build --sot-path ./sot.sample --variant base --theme default --style-preset compact
```

## Quick HTML preview

```bash
uv run cvw dev serve --sot-path ./sot.sample --variant base
```

The live preview auto-rebuilds on SoT/theme changes and exposes lightweight
overlay controls:

- `t`: cycle theme
- `p`: cycle style preset
- `r`: rebuild with current settings

The HTML output is written to `dist/<variant>/cv.html`. The command will open
the preview URL in your browser unless `CVW_SKIP_OPEN=1` is set.

If the browser opener fails, open the preview URL (printed by the CLI). As a
fallback, open the file manually:

```bash
open http://127.0.0.1:8765
open dist/<variant>/cv.html
```

To force a specific browser:

```bash
CVW_BROWSER="open -a /Applications/Google\\ Chrome.app" uv run cvw dev serve --sot-path ./sot.sample --variant base
```

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
