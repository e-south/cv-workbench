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
| Preview outputs | Disposable invocation-scoped inputs and rendered files; excluded from run GC | [Preview artifacts](#preview-artifacts) |
| Generated run | Latest runs per workspace/project and variant, plus explicit retained IDs | `cvw runs gc --json` |
| Draft or project proposal | Registered expiration and keep/discard decisions | [Variant lifecycle](variant-lifecycle.md) |
| Content review copy | Editable bundle whose recorded source run is retained by GC | [Content review](review-contract.md) |
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
- `keep_reasons`: retained IDs with `explicit_keep`, `latest_in_scope`, and/or
  `review:<review-id>` and `draft:<draft-id>`.

A nonempty preview exits with code 2. An empty plan exits with code 0. Add
`--yes` to apply a plan recalculated from current state. It is not a frozen
approval token; rerun the preview after changing workspace contents.

The operation validates its configured root beneath `var/` and preflights every
deletion target. Symlink traversal and targets outside the run root are rejected
before removal begins. These checks apply to Python callers as well as the CLI.
Filesystem failures can still interrupt cleanup after some deletions; removed
directories are not transactionally restored.

## Review Dependencies

Content review packs persist `review-source.json`. GC retains the exact source
paths referenced by records under the configured reviews root, including damaged
run manifests. Invalid records stop cleanup before deletion. Source health is
visible through `context` and `status`; changed source bytes still protect the
run for recovery even though they prevent import.

Historical bundles without a source record and custom Python API bundles outside
the configured reviews root require explicit `--keep` retention. Standalone
imports have their own source references below; other patch proposals do not
implicitly retain runs. A run contains canonical text and selection metadata
needed to interpret edits.

Authored publication uses a separate source/export pair and hash-addressed
review packet outside the run store. `runs gc` does not remove those artifacts.

## Import Draft Dependencies

`ops/review/drafts.py::load_import_draft_sources` owns the retention projection
of import metadata. It reads the declared `source: import-docx`, normalized
relative `run_id`, and absolute `canonical_path` ending in `canonical.md`.
For sources inside the configured run store, the path and ID must agree.
References protect exact source directories, not another run with the same
basename. External source paths do not retain unrelated local runs.

Run GC preserves these references under the configured draft store independently
of recency, manifest health, canonical-byte freshness, and `apply_status`.
`ready_no_changes` and `review_diff_only` do not authorize discarding the
comparison baseline. A damaged or missing canonical file still protects its
remaining run directory for recovery. This projection does not validate
application eligibility or declare the source content current.

Directories containing `draft.json` or `imported.md`, and directories named
`import-*`, identify potential imports. Missing/malformed records, duplicate JSON
fields, unsupported source kinds, invalid paths, and directory/record symlinks
stop cleanup before deletion. Ordinary unregistered proposal folders without
import markers do not gain invented run dependencies.

For legacy imports without records, preserve the files and inspect their
historical evidence. Recover original provenance from a trusted copy if available;
do not manufacture it from today's hashes or a latest-run guess. Before an
explicit archive/discard decision, retain possible baselines with `--keep` or
archive the draft and its baseline evidence together outside cleanup-managed
stores. No automatic migration or live cleanup is implied.

`gc_runs` captures or reuses one `ConfigSnapshot` for run, review, and draft
locations. The CLI delegates root validation to that operation. This keeps one
request's settings coherent, not a filesystem-wide snapshot or writer lock.
Changed dependencies after inspection remain outside this guarantee; use an
idle workspace for deliberate cleanup. Existing partial-deletion I/O limits
still apply. See `tests/ops/review/test_draft_retention.py` for guarded deletion
in temporary fixtures and CLI plan behavior.

## Preview Artifacts

Preview owns `preview/` beneath the configured runs root, including the current
server lease and invocation-scoped variant/project directories. Successful files
survive one-shot exit or server stop so the returned path remains reviewable.
They carry no build manifest or review provenance and do not enter run catalogs,
latest-run selection, or `runs gc`, even with `--include-invalid`.

Preview does not automatically remove older invocations or legacy shared folders.
A dedicated preview-retention plan is not yet implemented. Whole-store
`cvw clean runs` includes this subtree and all audited runs; preserve needed
review/build artifacts and stop the preview server before explicitly applying
that broader cleanup. Do not use it as an automatic preview-only cleanup step.
The [preview contract](preview-contract.md#artifact-ownership) owns path semantics.

## Whole-store Cleanup

`cvw clean <store>` previews removal of an entire configured generated store;
`--yes` applies it. This bypasses the run-retention selection because it is an
explicit whole-store operation. Use run GC for routine gardening. Preserve
outstanding review/import dependencies before deliberately clearing a store.
