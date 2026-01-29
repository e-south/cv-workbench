# cv-workbench

[![CI](https://github.com/e-south/cv-workbench/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/e-south/cv-workbench/actions/workflows/ci.yml?query=branch%3Amain)

A lean, decoupled CV/Resume workbench. This repo is the public engine; real CV
content lives in a private Source of Truth (SoT) directory outside this repo.

Key goals:
- Deterministic builds from structured SoT
- Variant generation via data + filters
- Auditable outputs (local run manifests)
- MCP-ready CLI surface (`validate`, `build`, `render`, `tailor`, `diff`, `sync`)

## Table of contents

- [Quickstart](#quickstart)
- [Docs](#docs)
- [Repository layout](#repository-layout)
- [License](#license)

## Quickstart

Requirements:
- Python 3.12
- uv (https://docs.astral.sh/uv/)
- Pandoc (for rendering)
- LaTeX engine (xelatex) for PDF output

macOS (Homebrew):
```bash
brew install pandoc mactex-no-gui
eval "$(/usr/libexec/path_helper)"
```

```bash
uv sync --locked
uv run cvw --help
uv run cvw init
uv run cvw doctor
uv run cvw quickstart
uv run cvw validate --sot-path ./sot.sample
uv run cvw build --sot-path ./sot.sample --variant base --format md,pdf
```

Build output locations are printed after `cvw build` completes, and artifacts
are written under `dist/<variant>/` (configurable via `config/workbench.yaml`).

Tip: you can run `cvw` from any subdirectory in the repo. The CLI resolves the
nearest `config/workbench.yaml` by walking up parent directories, so outputs
still land under the configured `dist/`, `runs/`, `drafts/`, and `reviews/`
paths.

See the full walkthrough at `docs/howto/quickstart.md`.

## Docs

- `docs/concepts/overview.md`: CLI surface and feature overview
- `docs/concepts/architecture.md`: design principles and planes
- `docs/howto/quickstart.md`: step-by-step local setup
- `docs/howto/ingestion.md`: URL ingestion + registry layout
- `docs/howto/performance.md`: profiling guidance
- `docs/reference/site-contract.md`: Astro site sync contract
- `docs/reference/security.md`: security posture
- `docs/plans/dev-plan.md`: active roadmap

## Repository layout

- `config/`: global config and variants
- `registry/`: local context registry for ingested URLs (ignored by git)
- `reviews/`: review packs (DOCX/PDF + checklist, ignored by git)
- `build/`: templates, filters, styles, scripts
- `docs/`: concepts, how-to guides, reference, and plans
- `sot.sample/`: fake data for tests and examples
- `src/`: CLI and core logic

## License

MIT
