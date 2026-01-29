# Overview

cv-workbench is a public, deterministic CV/resume build engine. Personal content
lives in a private SoT directory and is never committed here.

The CLI is designed as a clean tool surface for MCP and other orchestration:
- validate
- build
- render
- tailor
- diff
- sync

Each command is single-purpose and composable.

Variants can target different document types (resume, cover-letter). Tag filters
apply to bullet entries and cover-letter sections for consistent selection.

## Dependency management

- Locked install (recommended): `uv sync --frozen`
- Update dependencies: `uv lock` then `uv sync`

uv uses `--frozen` for locked installs (it will not modify `uv.lock`).
