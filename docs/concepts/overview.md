---
id: concepts-overview
intent: Explain the workbench value, document workflows, and capability boundaries.
audience: [operator, agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Overview

cv-workbench turns private career records into tailored, reviewable professional
documents. Its value is reducing repeated formatting and selection work while
making the source, proposed changes, rendered version, and publication decision
traceable. The public repository contains the engine and examples; personal
content lives outside git.

## Choose the document workflow

| Intended outcome | Editable authority | Workflow and next reference |
| --- | --- | --- |
| Generate a resume or cover letter with repeatable selection and styling | Structured Source of Truth (SoT), variant, and theme | [Build and preview](../howto/quickstart.md), then [styling](../howto/styling.md) |
| Tailor content for an opportunity without changing the career record during review | Project proposal over the structured SoT | [Guide, author, build, review, and apply](../reference/project-contract.md) |
| Publish a CV that retains an authored Word layout | Private DOCX and its corresponding local PDF export | [Prepare, inspect, review the exact PDF, and sync](../howto/publish-site.md) |

Generated resume preview and authored CV publication use different source
authorities. A generated preview cannot establish the layout quality of the
authored public CV. Project application changes the structured source; it does
not rewrite the authored DOCX.

## What makes the workflow dependable

- Source facts, proposed edits, retained runs, previews, and publication records
  have distinct owners. See [architecture](architecture.md).
- Supported edits name stable targets and expected source text. Review can
  precede source changes; see [project editing](../reference/project-contract.md#patch-format).
- A build records selection and provenance so a reviewer can identify the
  artifact and inputs. Local [verification](../reference/verify-contract.md)
  exercises complete CLI journeys as well as boundary tests.
- Public preparation checks disclosure and fidelity; a separate review binds
  to the exact PDF. See [publication](../reference/publication-contract.md).

The CLI exposes callable operations through explicit commands and JSON results
for both operators and automation. Use [the workflow router](../readme.md#usage-flows)
for an outcome, `cvw workflow` for available recipes, and `cvw --help` for the
current verb list.

## Capabilities and limits

Primary feature lanes:
- `tailor` scaffolds a deterministic draft from a job file. It copies the base
  variant, snapshots the job text, emits `signals.json` and `prompt.json`, and
  leaves `patch.diff` empty until an operator or agent authors a proposal.
- `project guide` and `project new` create project-local tailoring workspaces
  with a proposal `variant.yaml` plus `project-ops` `patch.yaml`. Supported
  executable ops are intentionally narrow: guarded experience bullet
  replacement and project summary replacement.
- `reviewpack` packages immutable build artifacts for review. `import-docx`
  maps supported reviewed edits back into structured `patch.yaml`; unsupported
  edits fall back to `patch.diff` and `review_diff_only`.
- Export is a `build` / `render` outcome, not a separate command. `preview` is
  a local-only render-control UI for inspecting and rebuilding outputs.

`uv run cvw workflow` renders the same recipe contract exposed by
`uv run cvw context --json`, but in a smaller human-readable form that is more
useful for operator logs and agent handoff. Use
`uv run cvw workflow --id <recipe> --json --compact` when you want narrow,
recipe-only retrieval instead of the full workspace summary.

`uv run cvw context --json --compact` provides the same bootstrap state in a
summary-only machine-readable form with recommended follow-up workflows.

`uv run cvw build` prints the dist/run output paths so you can immediately locate the
generated CV artifacts and manifests.

Selection metadata is written to `selection.json` for explainable filtering.

Variants can target different document types (resume, cover-letter). Tag filters
apply to bullet entries and cover-letter sections for consistent selection.
`contact_fields` explicitly selects top-level contact data; public policy can
also forbid sections such as references before site sync.

URL ingestion creates local registry entries under `var/registry/contexts/` and
stores extracted text, deterministic signals, and a draft strategy file.

Tags are normalized (case/punctuation-insensitive) and can be namespaced using
`namespace:value` syntax (for example, `domain:synthetic-biology`). Namespaced
tags also register the namespace as a tag, enabling broader include/exclude
rules like `domain`.

Publication author roles are rendered via `build/filters/author_roles.lua` with
default markers (co-first `*`, corresponding `†`, senior `‡`).

## Dependency management

- Locked install (recommended): `uv sync --locked`
- Update dependencies: `uv lock` then `uv sync`

## Optional SoT sections

If present, the workbench can also ingest:
- `publications.yaml`
- `honors.yaml`
- `service.yaml`
- `teaching.yaml`
- `conferences.yaml`
- `references.yaml`

## Snippets

Snippets are small markdown blocks used to override summaries or add section
introductions without editing YAML fields. Define them in `snippets.yaml` and
store the content in `snippets/`.

Supported scopes:
- `summary` (overrides `person.summary`)
- `section-intro` (adds a paragraph after a section heading)
- `letter-open` (inserted after the salutation)
- `letter-close` (inserted before the closing)

Example `snippets.yaml`:
```yaml
snippets:
  - id: summary
    scope: summary
    path: snippets/summary.md
  - id: experience-intro
    scope: section-intro
    section: experience
    path: snippets/experience.md
```
