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

- `var/dist/base/cv.md`
- `var/dist/base/cv.pdf`
- `var/dist/base/cv.docx`
- `var/dist/base/manifest.json`
- `var/runs/<timestamp>/canonical.md`
- `var/runs/<timestamp>/resume.json`
- `var/runs/<timestamp>/selection.json`

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
uv run cvw preview --sot-path ./sot.sample --variant base --style-preset modern
uv run cvw preview --sot-path ./sot.sample --variant base --style-preset compact
```

`cvw preview` starts a live preview server and auto-rebuilds when you edit SoT
files, theme templates, or style presets. The command prints a local preview URL;
use Playwright to open and interact with the preview UI (sidebar controls and
shortcuts). The sidebar controls (or shortcuts) let you cycle themes, presets,
variants, and formats:

- `t`: cycle theme
- `p`: cycle style preset
- `v`: cycle variant
- `f`: cycle format (HTML/PDF/MD/ATS)
- `r`: rebuild with current settings
- `x`: stop the preview server

Closing the browser tab does not stop the preview server. Use the Stop button
(or `x`) in the control bar, or run:

```bash
uv run cvw dev stop
```

To change the host or port:

```bash
CVW_DEV_HOST=0.0.0.0 CVW_DEV_PORT=8877 uv run cvw dev serve --sot-path ./sot.sample --variant base
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

`cvw tailor` writes draft variants to `var/drafts/` and registers them as
ephemeral. Promote only the ones you want to keep:

```bash
uv run cvw variant keep --path ./var/drafts/<name>/variant.yaml --id <variant-id>
```

To discard or clean up drafts:

```bash
uv run cvw variant discard --path ./var/drafts/<name>/variant.yaml --yes
uv run cvw variant gc --yes
```

List pending drafts with:

```bash
uv run cvw variant inbox
```

The retention window is controlled by `variant_lifecycle.ttl_days` in
`config/workbench.yaml`.

## 9) Start a project (job tailoring)

```bash
uv run cvw project new --job-url "https://example.com/job" --variant base
uv run cvw preview --project <project-id>
```

Projects keep job context, signals, and proposal drafts without mutating SoT.

## 10) Clean generated artifacts

```bash
uv run cvw clean runs --yes
uv run cvw clean dist --yes
uv run cvw clean drafts --yes
uv run cvw clean reviews --yes
uv run cvw clean registry --yes
uv run cvw clean projects --yes
```

Clean commands default to a dry run unless `--yes` is provided.
