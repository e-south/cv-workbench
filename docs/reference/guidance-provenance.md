---
id: reference-guidance-provenance
intent: Define the inputs recorded with saved project guidance and the limits of their comparison.
audience: [operator, agent, maintainer]
status: active
navigation:
  parent: project-contract.md
---

# Saved guidance input provenance

`project guide` records the inputs used to produce its recommendation in
`job/proposal-plan.json`. `project show --json` compares that record with current
local observations. Preview shows the same diagnostics from its last successful
rebuild. A match concerns the declared guidance inputs, not the complete source
document, rendered output, or publication approval.

## Input record

The plan's `provenance` object declares `schema: cvw-guidance-inputs-v1`,
`algorithm: tag-overlap-v1`, and a `components` mapping with five SHA-256 digests:

| Component | Input represented |
| --- | --- |
| `extracted_text` | Exact UTF-8 bytes captured from the stored extracted job text. |
| `signals` | Exact UTF-8 JSON bytes captured from the stored signals file. |
| `source_tags` | Normalized source tag counts consumed by recommendation scoring. |
| `variant_catalog` | Candidate IDs, document types, and include/exclude tags consumed by ranking. |
| `default_variant` | The default variant ID consumed by scoring and rationale. |

Job parsing and fingerprints use the same captured bytes. Tag counts and catalog
values come from the already loaded guidance inputs; the producer does not reread
files to construct a later provenance record. Job input captures share the
project-owned regular-file checks in `artifacts.py`.

Structured inputs use UTF-8 JSON with sorted object keys, compact separators,
unescaped Unicode, and no nonfinite numbers. Catalog tags are sets represented
as sorted lists; candidate projections are sorted by their sorted-key JSON text.
Catalog paths, output formats, styling, and other fields outside ranking are
excluded. Ranking and fingerprints share `guidance_catalog_inputs` so they consume
the same catalog projection. Source prose edits that leave tag counts unchanged
do not change `source_tags`.

The schema identifies the fingerprint representation. The algorithm identifier
is owned by `guidance.py`; bump it when scoring, normalization, evidence
interpretation, or consumed input semantics change. Bump the schema when the
record format or canonical representation changes. Readers reject unsupported
identifiers, missing/extra components, and malformed digests as unverifiable.

## Inspection API and states

`cvworkbench.ops.projects.inspect_guidance_inputs(plan, details=details,
config_path=config, sot_path=None)` returns a `GuidanceInputCheck` with `state`,
`changed`, `unavailable`, and safe `errors`. Pass freshly loaded
`load_project_details` and `load_project_plan` results to refresh observations.
The supplied detail record's artifact observations are reused; job files are not
reread behind the caller's back. `config_path` accepts a path or `ConfigSnapshot`.
Passing `None` leaves catalog/default inputs unavailable instead of guessing a
configuration.

| State | Meaning |
| --- | --- |
| `matches_inputs` | All five compared inputs match the supported saved record. |
| `changed` | At least one input differs; `changed` names it. Other inputs may still be unavailable. |
| `unverifiable` | Provenance is absent/unsupported/malformed, or no change is known but some inputs cannot be compared. |

Job digests are compared with the saved plan's fingerprints, independently of the
current `project.yaml` hashes. Source/catalog/default comparisons use current
local inputs. Known changes remain visible if another comparison is unavailable.
Read and schema failures do not rewrite the plan or hide other project details.
Older plans remain readable with an explicit missing-provenance diagnostic;
inspection does not retrofit a record that would imply historical knowledge.

CLI JSON includes `guidance_inputs`, a display `guidance_input_status`, and an
optional `guidance_input_warning`. Plain/rich summaries and preview show the
same status and warning. Preview uses the underlying source selected for its
build, including an explicit source override, before project patch application.
It caches these observations until another successful rebuild.

## Limits and ownership

This record is not authenticated. Editing both a plan's fingerprints and its
inputs can produce a match. Inspection does not fetch the original job URL,
reread the original job file, or prove the freshness of the complete source or
rendered documents. Config settings, source/catalog reads, and artifact
observations have separate lifetimes; they are not a locked filesystem snapshot.

`provenance.py` owns record validation and comparison. `guidance.py` owns ranking
semantics and its catalog projection; `artifacts.py` owns job-byte capture and
file observations. Workspace code owns status wording. CLI and preview consume
those APIs rather than reconstructing fingerprints. See the broader
[project contract](project-contract.md#python-ownership) for lifecycle ownership.
