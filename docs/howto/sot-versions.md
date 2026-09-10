---
id: howto-sot-versions
intent: Guide isolated Source of Truth version experiments and activation.
audience: [operator, agent]
status: active
navigation:
  parent: ../readme.md
---

# SoT version packs

Use version packs to experiment safely without overwriting your canonical SoT.
Each version lives under `local/sot/versions/<name>/`, with `local/sot/ACTIVE` selecting the
current version.

When applying an edit, pass the pack root to select `ACTIVE`, or pass a concrete
`versions/<name>` directory to keep that edit pinned. The command reports the
directory it edited. See the [application selection contract](../reference/patch-application.md#source-selection)
for project defaults, invalid-pack errors, and in-flight selection behavior.

## List versions

```bash
uv run cvw sot list
```

## Create a new version

```bash
uv run cvw sot new experiment --from base
```

If `--from` is omitted, the active version is used as the base.

## Activate a version

```bash
uv run cvw sot activate experiment
```

## Diff versions

```bash
uv run cvw sot diff base experiment
```

Diffs normalize YAML keys to keep output stable and readable.
