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

## Build ownership

| Responsibility | Owner beneath `src/cvworkbench/` |
| --- | --- |
| Read-only content and render planning | `build/planning.py` |
| Explicit render-input fingerprints and lifetime checks | `build/assets.py` |
| Bundle membership and temporary artifact generation | `build/artifacts.py` |
| Build lifetime and commit orchestration | `build/pipeline.py` |
| Exclusive run allocation and owned-directory cleanup | `build/runs.py` |
| Recoverable file replacements shared by workflows | `storage.py` |

The [build recovery contract](../reference/configuration-contract.md#build-bundle-recovery)
defines staging, captured output preconditions, rollback, and concurrency limits.
Build code must not depend on operations merely to reuse file persistence.

Preview uses `dev/preview_paths.py` to separate canonical input from served
output and assign an independent directory to each invocation. Audited builds,
preview artifacts, and publication records have distinct ownership and retention
rules; see [preview ownership](../reference/preview-contract.md#artifact-ownership).

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

## Workspace inspection and command adapters

`workspace/context.py::inspect_workspace` composes local inventories into the
context payload. It has no terminal output and performs no workspace writes.
`workspace/status.py::inspect_status` uses the same inventory owners for the
validated-source status view and preserves individual source diagnostics.
CLI adapters own command parsing, output formatting, and exception-to-exit-code
translation. The [context contract](../reference/context-contract.md#python-inspection-api)
defines the callable API and its error semantics.

`workspace/projects/` groups project inventory, shared full/preview inspection,
command descriptions, and guidance presentation. Its
[inspection contract](../reference/project-inspection.md) defines the two
projections and their distinct error and read-cost boundaries.

| Responsibility | Owner beneath `src/cvworkbench/` |
| --- | --- |
| Source files, sections, tags, and version inventory | `workspace/source.py` |
| Configured variants and proposal inbox | `workspace/variants.py` |
| Build history and review readiness | `workspace/runs.py` |
| Project inventory | `workspace/projects/inventory.py` |
| Full project inspection and preview observations | `workspace/projects/inspection.py` |
| Available project command descriptions | `workspace/projects/commands.py` |
| Job evidence, variant recommendations, and proposal planning | `ops/projects/guidance.py` |
| Project metadata, proposal inspection, and bounded saved-plan reads | `ops/projects/inspection.py` |
| Stored job-file observations against recorded digests | `ops/projects/artifacts.py` |
| Source copies for guarded project edits and owned failure cleanup | `ops/projects/preparation.py` |
| Project build validation and retained-run orchestration | `ops/projects/building.py` |
| Saved guidance input fingerprints and comparison | `ops/projects/provenance.py` |
| Saved-guidance selection warnings and recommendation summaries | `workspace/projects/guidance.py` |
| Content-review inventory and source health | `workspace/reviews.py` |
| Authored publication state and review/sync recipe | `workspace/publication.py` |
| Command quoting and workspace/source argument propagation | `workspace/commands.py` |
| Recipe selection and ordering | `workspace/workflows/catalog.py` |
| Setup, build, review, project, and maintenance recipe descriptions | Corresponding modules in `workspace/workflows/` |
| Step metadata and state-based recommendations | `workspace/workflows/steps.py`, `recommendations.py` |

CLI adapters call workspace inspection or operation APIs, which share lower
input owners. Workspace code does not import CLI/preview controllers or terminal
libraries; build and input code do not import operations, workspace inspection,
or adapters. Operations do not import workspace inspection. Architecture tests
in `tests/workspace/test_boundaries.py` enforce these import directions, including
local and relative imports. Describing a command never executes it.

Inspection reuses each validated source payload for its section/tag summaries.
This is not a transaction across all configuration and artifact reads.
`config.py::ConfigSnapshot` gives build, render, workspace inspection, and
publication inspection an explicit immutable workbench configuration generation,
recorded by hash in build manifests. Workflow descriptions receive resolved
locations without selecting settings themselves. The
[configuration contract](../reference/configuration-contract.md) defines
resolution, preflight, and the remaining adoption boundaries. Project and several
other command adapters retain orchestration that can move behind operation APIs as
their behavior is characterized.

`ops/projects/` groups project identity, manifests, inspection, creation,
guarded content edits, and recommendation logic behind an explicit public API.
The [project ownership contract](../reference/project-contract.md#python-ownership)
defines the internal modules. Variant catalog loading lives in `variants.py`,
so project operations and workspace inventory share it without importing each
other. These ownership boundaries do not imply that all CLI orchestration has
already moved into operations. Guided project creation is owned by
`ops/projects/workflow.py::guide_project`; its adapter owns presentation and
optional preview launch. The [guidance API](../reference/project-contract.md#guidance-api)
defines result, error, configuration, and recovery semantics.

`build/planning.py` resolves content and render choices without writing artifacts.
`inputs/sot.py` and `variants.py` capture fingerprints alongside the content they
parse. The plan carries those fingerprints to `build/manifest.py`, so manifest
collection does not acquire a different generation of source or variant files.
`build/pipeline.py` executes the resulting request-local plan; `build_documents`
composes those phases for ordinary callers. `build/rendering.py` owns staged
output promotion for both individual and batch renders; callback ordering and
failure recovery share that boundary. `ops/projects/building.py` combines
temporary source preparation, schema validation, and that same plan before
allocating a retained project run. Its CLI adapter delegates to `build_project`
and presents the result. The [project build API](../reference/project-contract.md#project-build-api)
and [build input lifetime](../reference/configuration-contract.md#build-and-render-boundaries)
define the boundary; a plan is not a persistent input snapshot.

## Command adapters

`cli/app.py` registers public commands and groups. It contains no workflow
function bodies or domain imports. Implementations live beneath `cli/commands/`;
the registered command names, flags, help, output modes, and error messages are
their public contract. Python callers use the workspace or operation APIs for
workflow data rather than depending on command adapters or their private helpers.

| Command responsibility | Owner beneath `cli/commands/` |
| --- | --- |
| Validation, toolchain checks, initialization, first build | `setup.py` |
| Status, context, bootstrap, workflow guidance | `workspace.py` |
| Source versions and tags | `source.py` |
| Theme and preset inspection | `themes.py` |
| Local preview/server lifecycle | `preview.py` |
| Variant inventory, promotion, and lifecycle | `variants.py` |
| Run retention and generated-artifact cleanup | `maintenance.py` |
| Document build/render, comparison, and content review | Corresponding modules in `documents/` |
| Job ingestion, draft tailoring, and draft application | `tailoring.py` |
| Project creation/inspection, guidance, patch authoring, and presentation | Corresponding modules in `projects/` |
| Authored publication preparation, status, review, and sync | `publication.py` |

Command owners may use shared mechanics in `cli/helpers.py` and terminal
formatting in `cli/output.py`. They do not import the entrypoint. Project/setup
adapters that open a preview call the preview adapter directly; lower layers
retain their prohibition on CLI imports. Architecture tests protect the
registration-only entrypoint and these import directions, including relative
imports. Existing project workflow decisions remain an operation-API extraction
target; moving an adapter does not by itself turn its decisions into domain APIs.

## Preview presentation boundary

`dev/preview.py` owns the local controller and server; `dev/preview_http.py`
owns request validation. The page markup, styles, and browser interactions live
under `dev/assets/preview/`. `dev/presentation.py` assembles those package assets
into one HTML response. It contains no workflow or source-selection decisions
and adds no browser asset requests. UI layout and interaction changes belong in
these assets; build and publication decisions remain in their Python owners.

The personal site is a downstream presenter, not another CV compiler. Editable
review artifacts remain local to the workbench; the public site exposes one PDF
view/download surface.

Local context ingestion writes extracted text, deterministic signals, and draft
strategy files under `var/registry/contexts/` for auditability.
