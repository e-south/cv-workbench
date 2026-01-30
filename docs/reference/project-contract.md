# Project Contract

Projects are local, private workspaces for job tailoring. They keep job context,
signals, and proposal drafts without mutating the Source of Truth unless you
explicitly apply a patch.

## Default location

Projects live under `projects/` by default (gitignored). Override the path in
`config/workbench.yaml`:

```yaml
paths:
  projects: ../projects
```

## Layout

```
projects/<slug>/
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
