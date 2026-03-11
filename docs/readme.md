# Documentation Index

This is the central route map for `cv-workbench` workflows, command contracts,
and maintainer references. Use it to choose the smallest correct document for a
task instead of browsing the whole docs tree.

## Use This Index

1. Start with [Workflow routes](#workflow-routes) when you know the outcome you need.
2. Follow the route's "Verify next" target before moving into a downstream flow.
3. Use [Command and contract docs](#command-and-contract-docs) when scripting or building agent prompts.
4. Use [Guides by audience](#guides-by-audience) when you need the maintainer-only routes.
5. Return here as the canonical docs map; keep the root [README](../README.md) lightweight.

## Workflow Routes

| Need | Start here | Verify next |
| --- | --- | --- |
| Bootstrap a fresh workspace or get the first sample build | [howto/quickstart.md](howto/quickstart.md) | [reference/context-contract.md](reference/context-contract.md) |
| Capture a machine-readable workspace snapshot for automation | [reference/context-contract.md](reference/context-contract.md) | [concepts/overview.md](concepts/overview.md) |
| Inspect workspace state, tags, runs, or explainable selection | [concepts/overview.md](concepts/overview.md) | [reference/context-contract.md](reference/context-contract.md) |
| Run an explicit build or one-shot verification pass | [howto/quickstart.md](howto/quickstart.md) | [reference/preview-contract.md](reference/preview-contract.md) |
| Run the repo-local verify harness in an isolated workspace | [reference/verify-contract.md](reference/verify-contract.md) | [reference/preview-contract.md](reference/preview-contract.md) |
| Inspect the local preview UI or drive rebuilds safely | [reference/preview-contract.md](reference/preview-contract.md) | [howto/styling.md](howto/styling.md) |
| Compare themes, presets, and export styling | [howto/styling.md](howto/styling.md) | [reference/preview-contract.md](reference/preview-contract.md) |
| Ingest a job and create a project-scoped proposal | [howto/ingestion.md](howto/ingestion.md) | [reference/project-contract.md](reference/project-contract.md) |
| Inspect, keep, discard, or clean up proposal variants | [reference/variant-lifecycle.md](reference/variant-lifecycle.md) | [reference/project-contract.md](reference/project-contract.md) |
| Package a review run and import reviewed DOCX edits | [reference/project-contract.md](reference/project-contract.md) | [howto/ingestion.md](howto/ingestion.md) |
| Work with versioned SoT directories or packs | [howto/sot-versions.md](howto/sot-versions.md) | [reference/context-contract.md](reference/context-contract.md) |
| Sync rendered outputs into a site repo | [reference/site-contract.md](reference/site-contract.md) | [reference/security.md](reference/security.md) |
| Profile build or preview performance | [howto/performance.md](howto/performance.md) | [concepts/architecture.md](concepts/architecture.md) |

## Command And Contract Docs

Use these when the CLI contract matters more than the broader workflow:

- [concepts/overview.md](concepts/overview.md): CLI surface and feature lanes
- [reference/context-contract.md](reference/context-contract.md): bootstrap payload, recipes, and compact machine mode
- [reference/preview-contract.md](reference/preview-contract.md): local-only preview server, API, and UI control hooks
- [reference/verify-contract.md](reference/verify-contract.md): repo-local tracer-bullet verification harness
- [reference/project-contract.md](reference/project-contract.md): project layout, review/import invariants, and guarded patch application
- [reference/variant-lifecycle.md](reference/variant-lifecycle.md): ephemeral draft/project proposal lifecycle
- [reference/site-contract.md](reference/site-contract.md): local-first site sync contract
- [reference/security.md](reference/security.md): local/private content boundaries and security posture
- [reference/journal.md](reference/journal.md): operator and maintainer journal surface

## Guides By Audience

Operators:
- [howto/quickstart.md](howto/quickstart.md)
- [howto/ingestion.md](howto/ingestion.md)
- [howto/styling.md](howto/styling.md)
- [howto/sot-versions.md](howto/sot-versions.md)
- [howto/performance.md](howto/performance.md)

Agents and automation:
- [reference/context-contract.md](reference/context-contract.md)
- [reference/preview-contract.md](reference/preview-contract.md)
- [reference/verify-contract.md](reference/verify-contract.md)
- [reference/project-contract.md](reference/project-contract.md)
- [concepts/overview.md](concepts/overview.md)

Contributors and maintainers:
- [concepts/architecture.md](concepts/architecture.md)
- [plans/dev-plan.md](plans/dev-plan.md)
- [dev/journal.md](dev/journal.md)

## Config And Example Surfaces

Configuration and sample assets:
- [config/workbench.yaml](config/workbench.yaml)
- [config/publish.yaml](config/publish.yaml)
- [config/site-sync.yaml](config/site-sync.yaml)
- [config/variants/base.yaml](config/variants/base.yaml)
- [local/sot/](local/sot/)
- [build/themes/default/theme.yaml](build/themes/default/theme.yaml)

Top-level repo entry points:
- [../README.md](../README.md)
- [../AGENTS.md](../AGENTS.md)

## Planning And Design Notes

Use these when you need historical design context or open planning records:

- [plans/dev-plan.md](plans/dev-plan.md)
- [plans/2026-01-29-cv-workbench-design.md](plans/2026-01-29-cv-workbench-design.md)
- [plans/2026-01-29-sync-diff-tailor-design.md](plans/2026-01-29-sync-diff-tailor-design.md)
- [plans/2026-01-29-ux-ingestion-design.md](plans/2026-01-29-ux-ingestion-design.md)
- [plans/2026-01-31-context-recipes-design.md](plans/2026-01-31-context-recipes-design.md)
- [plans/2026-01-31-preview-playwright-clean-refactor.md](plans/2026-01-31-preview-playwright-clean-refactor.md)
- [plans/2026-01-31-variant-lifecycle-design.md](plans/2026-01-31-variant-lifecycle-design.md)

## Scope

This index is intentionally a router, not a monolithic guide. Its job is to
make the next correct document obvious for operators, contributors, and agents.
