# Journal

## 2026-01-29
- Repo name: cv-workbench
- Python 3.12 pinned; MIT license
- Public engine with private SoT via --sot-path (no submodule)
- SoT YAML compiled to JSON Resume; PDF via Pandoc -> LaTeX
- Variants allow selection rules + AI-assisted rewrites (drafts only)
- Run manifests and AI logs stay local under runs/
- Sync default is PR automation to site repo
- Outputs include short resume, long CV, cover letters
- LLM integration via Codex CLI
- Pre-commit uses ruff + gitleaks
- Documented uv lock and locked installs via `uv sync --frozen`
- Added canonical markdown materialization scaffolding and variant metadata defaults
- Added build pipeline with Pandoc filters for tag selection and bullet limits
- Documented Pandoc and LaTeX prerequisites for PDF rendering
- Added manifest generation with SoT hashes and tool metadata written to dist/ and runs/
- Added JSON Resume materialization to run outputs and tracked resume hashes in manifests
- Added strict schema validation with pydantic models and extra-field rejection
- Implemented render command plus shared path helpers
- Fixed markdown date formatting for year-only values
- Added sync, diff, and tailor command implementations with tests
- Added site sync config publish variant support and design notes
