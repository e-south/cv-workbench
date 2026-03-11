# cv-workbench

[![CI](https://github.com/e-south/cv-workbench/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/e-south/cv-workbench/actions/workflows/ci.yml?query=branch%3Amain)

A deterministic CV/resume workbench. This repository is the public engine;
private CV content lives in a separate Source of Truth (SoT) directory outside
git.

The project is organized for narrow, composable workflows:
- deterministic build and preview
- job-specific project proposals
- guarded SoT patching and import
- auditable runs, review packs, and selection metadata

## Quickstart

- Python 3.12
- uv
- Pandoc (for rendering)
- LaTeX engine (xelatex) for PDF output

```bash
uv sync --locked
uv run cvw init --sample-default
uv run cvw doctor
uv run cvw quickstart
```

After that, choose one narrow lane:
- fastest sample build: `uv run cvw quickstart`
- deterministic agent bootstrap: `uv run cvw context --json --compact`
- explicit local build: `uv run cvw build --variant base --format md,pdf`
- local preview: `uv run cvw preview --variant base`
- job tailoring project: `uv run cvw project guide --job-file var/job.txt`

## Docs

Use [docs/readme.md](docs/readme.md) as the canonical docs index. It routes to
the smallest relevant document instead of forcing a monolithic guide.

High-value entry points:
- [Quickstart](docs/howto/quickstart.md): local setup and first successful build
- [Overview](docs/concepts/overview.md): CLI surface and feature lanes
- [Project contract](docs/reference/project-contract.md): project workspace and guarded patch flows
- [Preview contract](docs/reference/preview-contract.md): preview behavior and local-only UI contract

## Documentation Layout

- `docs/concepts/`: explanation and architecture
- `docs/howto/`: task-focused operator guides
- `docs/reference/`: contracts, invariants, and command behavior
- `docs/plans/`: roadmap and design notes

## Repository Layout

- `src/`: CLI and core logic
- `tests/`: regression coverage
- `config/`: workspace config and variants
- `sot.sample/`: safe sample SoT data
- `local/`: private SoT data (ignored)
- `var/`: generated runs, dist, drafts, reviews, and projects (ignored)
- `build/`: templates, filters, themes, and rendering assets

## Example Commands

```bash
uv run cvw workflow --id automation.verify --json --compact
uv run cvw project show <project-id>
uv run cvw reviewpack --project <project-id> --run projects/<project-id>/<run-id>
```

## License

MIT
