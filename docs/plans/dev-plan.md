# Dev plan

## Decoupling decisions
- Public engine, private SoT provided via `--sot-path`; no real CV data in git.
- YAML SoT compiled to JSON Resume as an internal interchange format.
- Build pipeline is deterministic; outputs are artifacts (`dist/`, `runs/`) and never committed.
- Site integration is an adapter (`sync`), keeping the Astro site as a consumer.
- MCP/tooling surface stays small and stable: validate, build, render, tailor, diff, sync.

## Validation posture
- Strict, assertive schema validation with extra fields rejected.
- Validation and build steps remain separate to keep error reporting explicit.

## Current state
- validate/build/render implemented with Pandoc + Lua filters.
- JSON Resume materialization emitted to `runs/<timestamp>/resume.json`.
- Manifests include SoT hashes, variant hash, and resume hash.

## Next todos
- Implement `sync` (local + PR modes) against the site contract.
- Add `diff` for variant comparisons (selection + output diffs).
- Add `tailor` scaffolding (proposal-only, Codex CLI shell-out).
- Expand render targets (HTML/DOCX) if/when needed.
- Add site contract tests and fixture coverage for cover letters and CV variants.
