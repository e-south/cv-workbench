# Documentation Index

This file is the docs router for `cv-workbench`. Use it to pick one narrow
document for the task at hand instead of loading the whole docs tree.

Documentation types in this repo:
- `concepts/`: explanation and mental models
- `howto/`: task-focused operator guides
- `reference/`: contracts, invariants, and command behavior
- `plans/`: roadmap and design notes

## Start Here

If you are new to the repo:
- first successful local build: [howto/quickstart.md](howto/quickstart.md)
- CLI and feature surface overview: [concepts/overview.md](concepts/overview.md)
- architecture and design boundaries: [concepts/architecture.md](concepts/architecture.md)

If you are using an agent or scripting against the CLI:
- workspace/bootstrap contract: [reference/context-contract.md](reference/context-contract.md)
- quickest machine-friendly setup path: [howto/quickstart.md](howto/quickstart.md)

## Choose By Goal

Build, preview, and local setup:
- local setup and first run: [howto/quickstart.md](howto/quickstart.md)
- preview behavior and constraints: [reference/preview-contract.md](reference/preview-contract.md)
- styling and theme/preset choices: [howto/styling.md](howto/styling.md)
- performance and profiling: [howto/performance.md](howto/performance.md)

Job tailoring and project workflows:
- feature summary and flow boundaries: [concepts/overview.md](concepts/overview.md)
- job ingestion and registry layout: [howto/ingestion.md](howto/ingestion.md)
- project workspace, guarded patching, and reviewpack sequencing: [reference/project-contract.md](reference/project-contract.md)
- variant promotion, inbox, discard, and cleanup: [reference/variant-lifecycle.md](reference/variant-lifecycle.md)

Review, import, and export:
- guided operator path: [howto/quickstart.md](howto/quickstart.md)
- project/run/review invariants: [reference/project-contract.md](reference/project-contract.md)
- preview/render behavior: [reference/preview-contract.md](reference/preview-contract.md)

Versioned SoT and publishing:
- SoT pack/version workflows: [howto/sot-versions.md](howto/sot-versions.md)
- site sync contract: [reference/site-contract.md](reference/site-contract.md)

## Choose By Doc Type

Concepts:
- [concepts/overview.md](concepts/overview.md)
- [concepts/architecture.md](concepts/architecture.md)

How-to guides:
- [howto/quickstart.md](howto/quickstart.md)
- [howto/ingestion.md](howto/ingestion.md)
- [howto/styling.md](howto/styling.md)
- [howto/sot-versions.md](howto/sot-versions.md)
- [howto/performance.md](howto/performance.md)

Reference:
- [reference/context-contract.md](reference/context-contract.md)
- [reference/project-contract.md](reference/project-contract.md)
- [reference/preview-contract.md](reference/preview-contract.md)
- [reference/variant-lifecycle.md](reference/variant-lifecycle.md)
- [reference/site-contract.md](reference/site-contract.md)
- [reference/security.md](reference/security.md)
- [reference/journal.md](reference/journal.md)

Maintainer planning:
- [plans/dev-plan.md](plans/dev-plan.md)
- [plans/2026-01-29-cv-workbench-design.md](plans/2026-01-29-cv-workbench-design.md)
- [plans/2026-01-29-sync-diff-tailor-design.md](plans/2026-01-29-sync-diff-tailor-design.md)
- [plans/2026-01-29-ux-ingestion-design.md](plans/2026-01-29-ux-ingestion-design.md)
- [plans/2026-01-31-context-recipes-design.md](plans/2026-01-31-context-recipes-design.md)
- [plans/2026-01-31-preview-playwright-clean-refactor.md](plans/2026-01-31-preview-playwright-clean-refactor.md)
- [plans/2026-01-31-variant-lifecycle-design.md](plans/2026-01-31-variant-lifecycle-design.md)

## Config And Repo Surfaces

Configuration examples and repo-visible config:
- [config/workbench.yaml](config/workbench.yaml)
- [config/publish.yaml](config/publish.yaml)
- [config/site-sync.yaml](config/site-sync.yaml)

Top-level repo entry points:
- [../README.md](../README.md)
- [../AGENTS.md](../AGENTS.md)

## Scope

This index is intentionally small. It is not a replacement for the detailed
how-to or reference docs; its job is to route operators, contributors, and
agents to the minimum relevant surface.
