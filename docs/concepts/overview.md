---
id: concepts-overview
intent: Explain the workbench capabilities and primary command surfaces.
audience: [operator, agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Overview

cv-workbench is a public, deterministic CV/resume build engine. Personal content
lives in a private SoT directory and is never committed here.

The CLI is designed as a clean tool surface for MCP and other orchestration:
- validate
- init
- quickstart
- doctor
- context
- workflow
- status
- build
- render
- preview
- dev serve
- clean (var/runs, var/dist, var/drafts, var/reviews, var/registry, var/projects)
- tailor
- diff
- sync
- explain
- reviewpack
- import-docx
- job add
- theme (list/info)
- variant (list/promote/keep/discard/gc/inbox)
- runs (gc)
- project (new/guide/show/apply)
- tags (list/lint/stats)
- sot (list/new/activate/diff)

Each command is single-purpose and composable.

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
