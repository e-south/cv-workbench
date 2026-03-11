# Variant Lifecycle

Variant drafts and project proposals are treated as ephemeral until you
explicitly keep them. The lifecycle is tracked locally so you can prune
inconsequential variants and keep only intentional ones.

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
- `uv run cvw variant gc --yes`: remove expired draft/proposal artifacts.

Use `uv run cvw variant promote` only for legacy scripts; `uv run cvw variant keep` is the
preferred path because it updates lifecycle state.
