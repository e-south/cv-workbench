# Architecture

This workbench separates three planes:

1) Source of Truth (SoT)
- Structured YAML input outside this repo
- Compiled to JSON Resume internally
- Cover letters share the same variant/tag system
- Letters live in `letters.yaml` and are selected via `variant.letter_id`

2) Deterministic build pipeline
- Validate SoT with strict schema checks
- Materialize canonical markdown
- Apply Pandoc Lua filters for variants (bullets and cover-letter sections)
- Render outputs (PDF via Pandoc -> LaTeX by default)
- Emit a local run manifest

3) Optional AI assistance
- Proposes drafts only (variants + patches)
- Never mutates SoT without explicit apply step

Outputs are always treated as build artifacts and are never committed.
