---
id: concepts-architecture
intent: Define the ownership boundaries and data flow of the workbench.
audience: [agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Architecture

This workbench separates four planes:

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
- Render sanitized review evidence under `var/reviews/publication/<pdf-sha256>`;
  page previews are a review surface, not another editable source
- Copy only the public PDF plus a sanitized provenance manifest
- Keep site presentation separate from CV selection and rendering

4) Optional AI assistance
- Proposes drafts only (variants + patches)
- Never mutates SoT without explicit apply step

Outputs are always treated as build artifacts and are never committed.

Configuration lives in the root `config/` tree, sample inputs in `sot.sample/`,
and theme assets in `build/themes/`. Documentation links to these owners rather
than maintaining executable copies beneath `docs/`.

## Distribution and workspace ownership

The wheel's `cvworkbench_data` package contains immutable rendering filters and
workspace templates. Explicit mappings in `pyproject.toml` bundle the canonical
sample inputs, themes, workbench settings, and base/cover-letter variants. The
neutral publication and destination templates live in `build/scaffold/config/`;
they deliberately contain no approved fingerprint or site path. The checkout's
configured `config/publish.yaml` and `config/site-sync.yaml` are not bundled.

`resources.py` resolves this data through `importlib.resources` for installed
and editable runtimes. Missing data is an installation error; runtime code does
not guess repository ancestors. `build/package/__init__.py` anchors the data
package so separate installations cannot merge their resource trees.

`init` validates template availability before creating the workspace, then
copies source examples and themes into editable workspace directories. Existing
files remain untouched, including the configured source path when
`--sample-default` is supplied again. `CVW_TEMPLATE_DIR` explicitly replaces the
workspace template root; it must contain the required sample, themes, workbench,
base variant, publication, and destination files. A cover-letter variant is
optional in a custom template and included in the shipped default.

After editing bundled defaults or filters in a checkout, refresh their installed
snapshot with `uv sync --reinstall-package cv-workbench`. Editing a workspace's
copied themes or configuration takes effect without reinstalling. The
[distribution test](../reference/verify-contract.md#installed-distribution)
checks this boundary with checkout imports excluded.

The personal site is a downstream presenter, not another CV compiler. Editable
review artifacts remain local to the workbench; the public site exposes one PDF
view/download surface.

Local context ingestion writes extracted text, deterministic signals, and draft
strategy files under `var/registry/contexts/` for auditability.
