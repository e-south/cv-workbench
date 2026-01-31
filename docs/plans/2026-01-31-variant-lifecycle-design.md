# Variant Lifecycle Design (2026-01-31)

## Goals

- Prevent buildup of low-signal variants by default.
- Require explicit keep/discard decisions.
- Keep flows deterministic, local-first, and fail-fast.
- Support human and agent workflows with minimal coupling.

## Non-goals

- Automatic promotion of variants without explicit keep.
- Silent cleanup of files outside `var/`.
- Backward-compatible soft defaults for missing lifecycle config.

## Approach (Option 1: Lifecycle Registry)

Introduce a local registry under `var/variants/registry.json` that tracks
ephemeral variants created by `tailor` and `project` flows. Each entry stores:

- `variant_id`, `variant_path`, `cleanup_path`
- `source` (`draft` or `project`)
- `status` (`ephemeral`, `kept`, `discarded`, `expired`)
- `created_at`, `expires_at`
- Optional metadata: `label`, `kept_path`, `kept_at`, `discarded_at`

Lifecycle decisions are made via explicit commands:

- `cvw variant inbox` to list pending items
- `cvw variant keep` to promote into `config/variants/`
- `cvw variant discard` to delete draft/proposal artifacts
- `cvw variant gc` to prune expired artifacts

## Configuration

Require an explicit TTL:

```yaml
variant_lifecycle:
  ttl_days: 7
```

If this value is missing or invalid, lifecycle operations (including `tailor`
and `project` creation) fail fast.

## Integration Points

- `cvw tailor`: registers draft variants at creation time.
- `cvw project new`: registers project proposal variants at creation time.
- `cvw variant promote`: remains available but does not update lifecycle state.

## Error Handling

- Registry parsing is strict; invalid entries raise errors.
- Cleanup paths must live under `var/` to prevent unsafe deletes.
- Discard/gc will not remove artifacts without an explicit `--yes`.

## Testing

- Unit tests for registry creation, keep/discard/gc flows.
- CLI tests for `tailor` and `variant` commands.
- Config parsing tests for TTL enforcement.
