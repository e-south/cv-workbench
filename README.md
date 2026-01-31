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
uv run cvw preview --sot-path ./sot.sample --variant base
```

Build output locations are printed after `cvw build` completes, and artifacts
are written under `var/dist/<variant>/` (configurable via `config/workbench.yaml`).

`cvw preview` starts a live preview server that auto-rebuilds on SoT, theme, and
variant changes. The command prints a local preview URL; use Playwright to open
and interact with the preview UI (sidebar controls and shortcuts `t`, `p`, `v`,
`f`, `r`, `x`). You can run `cvw dev stop` to stop the server.

Tip: you can run `cvw` from any subdirectory in the repo. The CLI resolves the
nearest `config/workbench.yaml` by walking up parent directories, so outputs
still land under the configured `var/dist/`, `var/runs/`, `var/drafts/`, and
`var/reviews/` paths.

See the full walkthrough at `docs/howto/quickstart.md`.

## Docs

- `docs/concepts/overview.md`: CLI surface and feature overview
- `docs/concepts/architecture.md`: design principles and planes
- `docs/howto/quickstart.md`: step-by-step local setup
- `docs/howto/ingestion.md`: URL ingestion + registry layout
- `docs/reference/project-contract.md`: project workspace contract
- `docs/reference/preview-contract.md`: preview UI/API contract
- `docs/howto/styling.md`: theme packs and style presets
- `docs/howto/sot-versions.md`: SoT version packs
- `docs/howto/performance.md`: profiling guidance
- `docs/reference/site-contract.md`: Astro site sync contract
- `docs/reference/security.md`: security posture
- `docs/plans/dev-plan.md`: active roadmap

## Repository layout

- `build/`: filters, themes, templates, styles, scripts
- `config/`: global config and variants
- `docs/`: concepts, how-to guides, reference, and plans
- `local/`: private SoT data (ignored by git)
- `var/`: generated artifacts (dist/runs/drafts/reviews/registry/projects; ignored by git)
- `sot.sample/`: fake data for tests and examples
- `src/`: CLI and core logic
- `tests/`: test suite

## License

MIT
