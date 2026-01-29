# cv-workbench design (2026-01-29)

## Goals
- Public, deterministic build engine
- Private SoT outside the repo
- MCP-ready CLI surface
- Reproducible builds with pinned tooling
- Auditability via local run manifests

## Key decisions
- SoT is YAML-first and compiled to JSON Resume internally.
- PDF default is Pandoc -> LaTeX/ConTeXt.
- Variants support selection rules and optional AI-assisted rewrites.
- Run manifests and AI logs stay local under `runs/` (not committed).
- Public engine + private SoT using a `--sot-path` contract (no submodules).
- Sync default is PR automation into the site repo.
- Outputs extend beyond CV: short resume, long CV, cover letters.
- LLM integration shells out to Codex CLI.
- Use uv for Python dependency management and lockfiles.
- Pre-commit includes ruff and gitleaks.

## CLI surface (MCP-ready)
- validate
- build
- render
- tailor
- diff
- sync

## High-level flow
1) Validate SoT and compile to JSON Resume
2) Materialize canonical markdown
3) Apply Pandoc Lua filters for variant selection
4) Render targets
5) Emit local run manifest
6) Sync outputs to site repo
