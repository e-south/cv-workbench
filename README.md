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
uv run cvw init --sample-default
uv run cvw doctor
uv run cvw context --json --compact
uv run cvw workflow --id automation.verify
uv run cvw workflow --id automation.verify --json --compact
uv run cvw quickstart
uv run cvw validate
uv run cvw build --variant base --format md,pdf
uv run cvw preview --variant base
```

`uv run cvw init` installs pre-commit hooks when a `.pre-commit-config.yaml`
is present in the repo. If hook installation fails, `init` prints
`pre_commit_hooks: error` plus a detail line with the underlying reason.

Use `--sample-default` in this public repo when you want the configured default
SoT to be `./sot.sample`. Omit the flag when you want `init` to copy the sample
into `./local/sot` for later replacement with private data.

Use `uv run cvw context --json --compact` when you want a smaller bootstrap
payload for logs, agent handoff, or scripting. It summarizes workspace state and
adds `recommended_workflows` with exact `command` and `json_command`
follow-ups. Treat the emitted strings as authoritative; outside the repo root
they may use `uv run --project <repo> cvw ...` so replay stays valid.
When the configured SoT is missing or invalid, those recommendations point to
the repair/bootstrap lanes before build or preview.

Build output locations are printed after `uv run cvw build` completes, and artifacts
are written under `var/dist/<variant>/` (configurable via `config/workbench.yaml`).

`uv run cvw preview` starts a live preview server that auto-rebuilds on SoT, theme, and
variant changes. The command prints a local preview URL; use Chrome DevTools MCP
to open and interact with the preview UI (sidebar controls and shortcuts `t`,
`p`, `v`, `f`, `r`, `x`). Browser inactivity now auto-stops the server after 30
seconds by default; use `uv run cvw dev stop` for immediate shutdown or set
`CVW_DEV_IDLE_TIMEOUT_SECONDS=0` to disable the idle timeout.

Tip: you can run `uv run cvw` from any subdirectory in the repo. When a
workspace already exists, commands such as `init`, `quickstart`, `context`,
`build`, and `preview` resolve the nearest `config/workbench.yaml` by walking up
parent directories, so outputs still land under the configured `var/dist/`,
`var/runs/`, `var/drafts/`, and `var/reviews/` paths.

See the full walkthrough at `docs/howto/quickstart.md`.

## Docs

- `docs/concepts/overview.md`: CLI surface and feature overview
- `docs/concepts/architecture.md`: design principles and planes
- `docs/howto/quickstart.md`: step-by-step local setup
- `docs/howto/ingestion.md`: URL ingestion + registry layout
- `docs/reference/project-contract.md`: project workspace contract
- `docs/reference/preview-contract.md`: preview UI/API contract
- `docs/reference/variant-lifecycle.md`: variant lifecycle and cleanup flows
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
