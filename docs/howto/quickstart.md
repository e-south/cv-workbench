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

## 2) Confirm the runtime toolchain

```bash
uv run cvw doctor
```

## 3) Build a sample CV

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

## 4) Build explicitly (recommended for automation)

```bash
uv run cvw build --sot-path ./sot.sample --variant base --format md,pdf
```

Use `--plain` for script-friendly text output or `--json` for machine-readable
payloads:

```bash
uv run cvw build --plain --sot-path ./sot.sample --variant base --format md
uv run cvw build --json --sot-path ./sot.sample --variant base --format md
```

## 5) Sync to your site (local-first)

```bash
uv run cvw sync --variant base --site /path/to/astro-site
```

`cvw sync` defaults to local mode. PR sync is opt-in via `--mode pr`.
