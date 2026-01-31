# SoT version packs

Use version packs to experiment safely without overwriting your canonical SoT.
Each version lives under `local/sot/versions/<name>/`, with `local/sot/ACTIVE` selecting the
current version.

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
