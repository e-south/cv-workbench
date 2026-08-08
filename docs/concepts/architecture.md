---
id: concepts-architecture
intent: Define the ownership boundaries and data flow of the workbench.
audience: [agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Architecture

This workbench separates three planes:

1) Source authorities
- Structured YAML input outside this repo
- Compiled to JSON Resume internally
- Cover letters share the same variant/tag system
- Letters live in `letters.yaml` and are selected via `variant.letter_id`
- Optional sections: publications, honors, service, teaching, conferences, references
- Optional snippets (`snippets.yaml` + `snippets/`) override summaries and add section intros
- A private editable DOCX owns the faithful layout of the public base CV; its
  PDF export is verified against that DOCX before publication

2) Deterministic build pipeline
- Validate SoT with strict schema checks
- Materialize canonical markdown
- Apply variant-owned contact-field and section selection
- Apply Pandoc Lua filters for variants (bullets and cover-letter sections)
- Render outputs (PDF via Pandoc -> LaTeX by default)
- Emit a local run manifest with output hashes
- Emit selection metadata for explainable filtering

3) Authored publication boundary
- Enforce public eligibility through `config/publish.yaml`
- Verify DOCX/PDF correspondence without re-typesetting the authored layout
- Redact prohibited content and reject unauthorized emails or hidden payloads
- Verify PDF type, variant metadata, and artifact hash again before writes
- Store reviewed publication artifacts under `var/publish`, never the generic
  `var/dist` build workspace
- Copy only the public PDF plus a sanitized provenance manifest
- Keep site presentation separate from CV selection and rendering

4) Optional AI assistance
- Proposes drafts only (variants + patches)
- Never mutates SoT without explicit apply step

Outputs are always treated as build artifacts and are never committed.

The personal site is a downstream presenter, not another CV compiler. Editable
review artifacts remain local to the workbench; the public site exposes one PDF
view/download surface.

Local context ingestion writes extracted text, deterministic signals, and draft
strategy files under `var/registry/contexts/` for auditability.
