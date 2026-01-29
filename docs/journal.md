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
