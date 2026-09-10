---
id: reference-variant-lifecycle
intent: Define ephemeral and retained proposal lifecycle semantics.
audience: [operator, agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Variant Lifecycle

Variant drafts and project proposals are treated as ephemeral until you
explicitly keep them. The lifecycle is tracked locally so you can prune
inconsequential variants and keep only intentional ones.

Variant selectors and promotion IDs follow the
[variant and artifact name contract](configuration-contract.md#variant-and-artifact-names).
They are identifiers, not filesystem paths.

## Configuration

Set the retention window in `config/workbench.yaml`:

```yaml
variant_lifecycle:
  ttl_days: 7
```

## Registry

Lifecycle state is stored in:

```
var/variants/registry.json
```

Entries include the source (`draft` or `project`), the variant file path, and
expiration metadata. The registry is local-only and gitignored.

Cleanup owns the variant file itself or its immediate bundle directory. Shared
containers such as `var/`, `var/drafts/`, and a project's parent directory are
not cleanup targets for a nested proposal.

## Commands

- `uv run cvw variant list`: show configured variants alongside pending lifecycle entries.
- `uv run cvw variant inbox`: list pending ephemeral variants. In `--json` mode it also
  emits selector-aware commands such as `keep_command`, `discard_command`, and
  `preview_command` for project proposals. Entries whose TTL has already
  elapsed are surfaced as `status="expired_pending_gc"` with a dry-run
  `gc_command` hint instead of silently looking identical to fresh proposals.
- `uv run cvw variant keep --path <variant.yaml> --id <variant-id>`: promote a draft or
  project proposal into `config/variants/`.
- `uv run cvw variant keep --project <project-id> --id <variant-id>`: promote a project
  proposal without reconstructing the raw `variant.yaml` path. `variant inbox`
  and `project show` now suggest a safe proposal id when the copied project
  variant still carries a colliding id such as `base`.
- `uv run cvw variant discard --path <variant.yaml> --yes`: discard a draft/proposal
  and delete its artifacts.
- `uv run cvw variant discard --project <project-id> --yes`: discard a project proposal by
  project selector instead of a raw path.
- `uv run cvw variant gc --json`: inspect expired entries without removing files
  or updating registry records. Each candidate reports `variant_id`,
  `cleanup_path`, `action`, and `reason`. A pending plan exits with code 2;
  an empty plan exits with code 0.
- `uv run cvw variant gc --yes`: apply the inspected lifecycle actions.

## Cleanup Plan

All eligible cleanup paths are validated before deletion starts. Paths outside
the workspace's `var/` root, the root itself, and paths that do not own the
registered variant bundle are rejected in both preview and apply modes.

- `action=remove` deletes an existing expired bundle.
- `action=reconcile` updates an expired record whose bundle is already absent;
  it does not delete a replacement or inferred target.
- `reason=expired` transitions an ephemeral entry to `expired`.
- `reason=kept_source` records source pruning while preserving the promoted
  variant and its `kept` status. Already-pruned sources are excluded from later
  plans.

`expired` and `kept_pruned` count planned lifecycle transitions in a dry run and
completed transitions on success. `reconciled` counts the subset whose targets
were already missing. A missing target remains visible in the inbox until an
explicit apply updates its record. No private workspace cleanup runs implicitly.

Filesystem failures during deletion still stop the operation; the preflight
does not promise transactional rollback of deleted directories.

Use `uv run cvw variant promote` only for legacy scripts; `uv run cvw variant keep` is the
preferred path because it updates lifecycle state.
