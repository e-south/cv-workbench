# cv-workbench

[![CI](https://github.com/e-south/cv-workbench/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/e-south/cv-workbench/actions/workflows/ci.yml?query=branch%3Amain)

A deterministic CV/resume workbench. This repository is the public engine;
private CV content lives in a separate Source of Truth (SoT) directory outside
git.

Use [docs/readme.md](docs/readme.md) as the canonical docs router. The root
README stays intentionally light; `docs/readme.md` routes the full workflow and
contract surface.

## Start Here

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

Common entry points:
- [First successful local build](docs/howto/quickstart.md)
- [Agent/bootstrap contract](docs/reference/context-contract.md)
- [Build and preview contract](docs/reference/preview-contract.md)
- [Job tailoring and project workflows](docs/howto/ingestion.md)
- [Review/import and guarded patching](docs/reference/project-contract.md)

Deterministic bootstrap commands:

```bash
uv run cvw context --json --compact
uv run cvw workflow --id automation.verify
uv run cvw workflow --id automation.verify --json --compact
```

## Core Workflows

- deterministic `build`, `render`, and `preview` flows
- project-scoped job tailoring with proposal variants and `project-ops` patches
- immutable run artifacts, review packs, and DOCX import drafts
- variant lifecycle, SoT versioning, and local site sync support

## Documentation Map

- [docs/readme.md](docs/readme.md): task-first docs index
- [docs/concepts/overview.md](docs/concepts/overview.md): CLI surface and feature lanes
- [docs/concepts/architecture.md](docs/concepts/architecture.md): repo boundaries and design constraints
- [docs/howto/](docs/howto/): operator guides
- [docs/reference/](docs/reference/): command contracts and invariants

## License

MIT
