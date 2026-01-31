# Project Contract

Projects are local, private workspaces for job tailoring. They keep job context,
signals, and proposal drafts without mutating the Source of Truth unless you
explicitly apply a patch.

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
- `cvw variant inbox` to list pending proposals.
- `cvw variant keep --path var/projects/<slug>/proposals/variant.yaml --id <new-id>`
  to promote a proposal into `config/variants/`.
- `cvw variant discard --path var/projects/<slug>/proposals/variant.yaml --yes` to
  discard proposal artifacts.
- `cvw variant gc --yes` to remove expired proposal artifacts.

## Apply semantics

- `cvw build --project <slug>` and `cvw preview --project <slug>` apply proposal
  patches in-memory.
- `cvw project apply <slug>` applies the patch to your SoT on disk.

## Patch format

`proposals/patch.yaml` uses a unified-diff payload:

```yaml
patch:
  format: unified-diff
  diff: ""
```

Empty diff means no changes.
