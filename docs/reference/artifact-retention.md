---
id: reference-artifact-retention
intent: Define ownership, retention decisions, and cleanup boundaries for generated artifacts.
audience: [operator, agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Artifact Retention

Build runs, review copies, and proposal variants have separate owners. Inspect
the relevant plan before applying cleanup; filesystem age alone does not prove
that an artifact is disposable.

| Artifact | Owner and retention rule | Inspect |
| --- | --- | --- |
| Generated run | Latest runs per workspace/project and variant, plus explicit retained IDs | `cvw runs gc --json` |
| Draft or project proposal | Registered expiration and keep/discard decisions | [Variant lifecycle](variant-lifecycle.md) |
| Content review copy | Operator-owned editable bundle; retain its source run explicitly | [Project review/import](project-contract.md) |
| Authored public PDF and review packet | Preparation snapshot and exact-PDF review state | [Publication lifecycle](publication-contract.md) |

## Run Cleanup

```bash
cvw runs gc --keep-latest 2 --keep projects/example/run-id --json
```

`--keep-latest` applies separately to each `(project, variant)` pair and to
workspace runs. A recent workspace build cannot displace a project's latest
run. Set it to zero only when retaining runs entirely by explicit ID.

`--keep` uses a full run ID relative to the configured runs root, including
`projects/<project-id>/<run-id>` for project runs. Explicit retention also
protects a directory with a missing or damaged manifest. Unknown IDs fail.

The JSON plan distinguishes:

- `candidates`: valid runs eligible for removal.
- `invalid`: all directories with missing or invalid run manifests.
- `invalid_candidates`: the subset eligible for removal when
  `--include-invalid` is selected, excluding explicitly retained IDs.
- `kept`: retained valid runs.
- `keep_reasons`: retained IDs with `explicit_keep` and/or `latest_in_scope`.

A nonempty preview exits with code 2. An empty plan exits with code 0. Add
`--yes` to apply a plan recalculated from current state. It is not a frozen
approval token; rerun the preview after changing workspace contents.

The operation validates its configured root beneath `var/` and preflights every
deletion target. Symlink traversal and targets outside the run root are rejected
before removal begins. These checks apply to Python callers as well as the CLI.
Filesystem failures can still interrupt cleanup after some deletions; removed
directories are not transactionally restored.

## Review Dependencies

Content review packs currently return their source run ID when created but do
not persist a durable run reference in the bundle. Keep that exact run explicitly
while editing or importing its DOCX. Run cleanup does not yet infer retention
from review copies or patch proposals. The run contains canonical text and
selection metadata needed to interpret edits correctly.

Authored publication uses a separate source/export pair and hash-addressed
review packet outside the run store. `runs gc` does not remove those artifacts.

## Whole-store Cleanup

`cvw clean <store>` previews removal of an entire configured generated store;
`--yes` applies it. This bypasses the run-retention selection because it is an
explicit whole-store operation. Use run GC for routine gardening. Preserve
outstanding review/import dependencies before deliberately clearing a store.
