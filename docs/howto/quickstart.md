# Quickstart

This guide walks through the fastest local path to a generated CV using the
sample SoT data. It is safe to run in this public repo.

## Requirements

- Python 3.12
- uv (https://docs.astral.sh/uv/)
- Pandoc (for rendering)
- LaTeX engine (xelatex) for PDF output

macOS (Homebrew):
```bash
brew install pandoc mactex-no-gui
eval "$(/usr/libexec/path_helper)"
```

## 1) Install dependencies

```bash
uv sync --locked
```

## 2) Initialize the workspace

```bash
uv run cvw init
```

## 3) Confirm the runtime toolchain

```bash
uv run cvw doctor
```

## 4) Build a sample CV

```bash
uv run cvw quickstart
```

This runs validation + build for the `base` variant and prints the output
locations. The default outputs are written to:

`cvw quickstart` also creates the default scaffold (config, variants, and
templates) if they are missing.

- `dist/base/cv.md`
- `dist/base/cv.pdf`
- `dist/base/cv.docx`
- `dist/base/manifest.json`
- `runs/<timestamp>/canonical.md`
- `runs/<timestamp>/resume.json`
- `runs/<timestamp>/selection.json`

You can run these commands from any subdirectory inside the repo. The CLI walks
up to the nearest `config/workbench.yaml` and resolves outputs relative to that
configuration.

## 5) Build explicitly (recommended for automation)

```bash
uv run cvw build --sot-path ./sot.sample --variant base --format md,pdf
```

Use `--plain` for script-friendly text output or `--json` for machine-readable
payloads:

```bash
uv run cvw build --plain --sot-path ./sot.sample --variant base --format md
uv run cvw build --json --sot-path ./sot.sample --variant base --format md
```

## 6) Sync to your site (local-first)

```bash
uv run cvw sync --variant base --site /path/to/astro-site
```

`cvw sync` defaults to local mode. PR sync is opt-in via `--mode pr`.

## 7) Preview styling quickly

```bash
uv run cvw theme list
uv run cvw dev serve --sot-path ./sot.sample --variant base --style-preset modern
uv run cvw dev serve --sot-path ./sot.sample --variant base --style-preset compact
```

`cvw dev serve` opens a live HTML preview and auto-rebuilds when you edit SoT
files, theme templates, or style presets. Use the overlay controls:

- `t`: cycle theme
- `p`: cycle style preset
- `r`: rebuild with current settings

If the browser does not open automatically, open the preview URL (printed in
the CLI summary). As a fallback, open the file directly:

```bash
open http://127.0.0.1:8765
open dist/<variant>/cv.html
```

To see a styling change, edit the preset CSS and let the watcher rebuild:

```bash
$EDITOR build/themes/default/styles/html/compact.css
```

If you want the PDF to reflect the same preset:

```bash
uv run cvw build --sot-path ./sot.sample --variant base --format pdf --style-preset compact
```

## 8) Save variants intentionally

`cvw tailor` writes draft variants to `drafts/`. Promote only the ones you want
to keep:

```bash
uv run cvw variant promote --draft ./drafts/<name>
```

## 9) Clean generated artifacts

```bash
uv run cvw clean runs --yes
uv run cvw clean dist --yes
uv run cvw clean drafts --yes
```

Clean commands default to a dry run unless `--yes` is provided.
