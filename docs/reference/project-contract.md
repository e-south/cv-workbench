# Project Contract

Projects are local, private workspaces for job tailoring. They keep job context,
signals, and proposal drafts without mutating the Source of Truth unless you
explicitly apply a patch.

## Commands

- `uv run cvw project guide --job-url <url>` or `--job-file <path>`: create a project
  and summarize SoT/job signals with variant recommendations.
- `uv run cvw project new --job-url <url>` or `--job-file <path>`: create a project
  without generating guidance output.
- `uv run cvw preview --project <slug> [--sot-path <path>]`: preview with project patch
  applied in-memory, optionally against an explicit SoT override.
- `uv run cvw reviewpack --project <slug>`: package the latest project-scoped run for review.
- `uv run cvw import-docx --from <docx> --project <slug>`: import a reviewed DOCX against
  the latest project-scoped canonical output.
- `uv run cvw project apply <slug>`: apply the patch to your SoT on disk.

## Default location

Projects live under `var/projects/` by default (gitignored). Override the path in
`config/workbench.yaml`:

```yaml
paths:
  projects: ../var/projects
```

## Layout

```
var/projects/<slug>/
  project.yaml
  job/
    source.url        # or source.path
    extracted.txt
    signals.json
    raw.html          # only if --store-raw
  proposals/
    variant.yaml
    patch.yaml
```

## Variant lifecycle

Project proposal variants are ephemeral until explicitly kept. They are tracked
in `var/variants/registry.json` and expire based on
`variant_lifecycle.ttl_days` in `config/workbench.yaml`.

Use:
- `uv run cvw variant inbox` to list pending proposals.
- `uv run cvw variant keep --project <slug> --id <new-id>` to promote a proposal into
  `config/variants/`.
- `uv run cvw variant discard --project <slug> --yes` to discard proposal artifacts.
- `uv run cvw variant gc --yes` to remove expired proposal artifacts.

## Apply semantics

- `uv run cvw build --project <slug>` and `uv run cvw preview --project <slug>` apply proposal
  patches in-memory.
- `uv run cvw reviewpack --run projects/<slug>/<run-id>` packages a specific project build
  deterministically when multiple runs exist.
- `uv run cvw project apply <slug>` applies the patch to your SoT on disk.

## Patch format

`proposals/patch.yaml` uses a unified-diff payload:

```yaml
patch:
  format: unified-diff
  diff: ""
```

Empty diff means no changes.

Project-scoped review packs default to `var/reviews/projects/<slug>/` so they do
not collide with variant-level review packs.
