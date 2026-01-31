# Dev plan

## Decoupling decisions
- Public engine, private SoT provided via `--sot-path`; no real CV data in git.
- YAML SoT compiled to JSON Resume as an internal interchange format.
- Build pipeline is deterministic; outputs are artifacts (`var/dist/`, `var/runs/`) and never committed.
- Site integration is an adapter (`sync`), keeping the Astro site as a consumer.
- MCP/tooling surface stays small and stable: validate, build, render, tailor, diff, sync.

## Validation posture
- Strict, assertive schema validation with extra fields rejected.
- Validation and build steps remain separate to keep error reporting explicit.

## Current state
- validate/build/render implemented with Pandoc + Lua filters.
- JSON Resume materialization emitted to `var/runs/<timestamp>/resume.json`.
- Manifests include SoT hashes, variant hash, and resume hash.
- sync/diff/tailor scaffolding implemented with tests.
- Cover-letter variants and tag filtering supported.
- HTML/DOCX render paths supported via Pandoc defaults.
- Draft signals generation and apply command implemented.
- Added optional SoT sections for publications, honors, service, teaching, conferences, and references.
- Added snippet support via `snippets.yaml` and `snippets/` (summary overrides + section intros + letter open/close).

## Gap audit (original spec → status)
- CLI surface: validate/build/render/tailor/diff/sync — Done
- Strict SoT schema validation — Done
- Variant selection + filters — Done (bullets + cover-letter sections)
- Multi-format output (md/pdf/html/docx) — Done
- Local + PR sync — Done (PR default, publish_variant enforced)
- AI proposal-only flow — Drafts only, apply done
- Apply step — Done
- Job ingestion signals — Done
- Manifest audit fields for AI steps — Pending
- Cover letters / CV variants — In progress (demo + semantics)
- Extended schema for academic CV sections — Done
- Snippet entrypoints for summaries + section intros — Done
- Security posture docs — Pending

## Next todos
- Extend manifest/logging for AI artifacts (prompt metadata, diff summary).
- Expand demo SoT and docs to cover cover letters and multi-variant examples.
