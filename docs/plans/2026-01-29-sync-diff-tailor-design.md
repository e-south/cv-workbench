# Sync, diff, and tailor design (2026-01-29)

## Goals
- Keep CV variants private by default.
- Preserve a small, stable MCP-ready CLI surface.
- Support rapid variant exploration with clear audit trails.

## Sync
- Default mode is PR-based.
- Sync only publishes a single configured public variant.
- The public variant comes from `config/site-sync.yaml` and is not overridable.
- Sync fails if the site repo has uncommitted changes.
- Sync derives the GitHub repo from the site repo `origin` remote.
- Local mode exists for manual workflows but is not the default.

## Diff
- Compares artifacts, not raw SoT.
- Each side can target `rendered` (default), `canonical`, or `resume`.
- Supports flexible `--run` and `--variant` selectors for each side.
- Output format supports unified diff (default) or JSON summary.

## Tailor
- `tailor` generates drafts only (variant + patch + prompt log).
- A separate `apply` command applies drafts.
- No automatic mutation of the SoT.
