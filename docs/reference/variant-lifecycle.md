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

- `cvw variant list`: show configured variants alongside pending lifecycle entries.
- `cvw variant inbox`: list pending ephemeral variants.
- `cvw variant keep --path <variant.yaml> --id <variant-id>`: promote a draft or
  project proposal into `config/variants/`.
- `cvw variant discard --path <variant.yaml> --yes`: discard a draft/proposal
  and delete its artifacts.
- `cvw variant gc --yes`: remove expired draft/proposal artifacts.

Use `cvw variant promote` only for legacy scripts; `variant keep` is the
preferred path because it updates lifecycle state.
