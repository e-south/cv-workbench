---
id: reference-patch-application
intent: Define captured patch inputs, source-write recovery, and supported diff boundaries.
audience: [operator, agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Patch application

`ops/patches.py` owns execution of unified diffs against a selected source
directory. Project operations and draft application share this boundary. Project
operation compilation still owns stable IDs and expected source text; draft
metadata still owns whether a reviewed edit is eligible to apply. See the
[project patch format](project-contract.md#patch-format) and
[review contract](review-contract.md).

## Operator behavior

`cvw project apply` and `cvw apply` share source-version selection. Preparation
for project builds/previews uses the same executor
against an owned source copy. Explicit application changes the selected source;
building or previewing does not authorize live source changes.

Application validates and captures the patch and its targets, runs the patch tool
in a temporary workspace, then commits completed edits. A malformed patch, tool
failure, or observed source edit leaves source files untouched by this operation.
Independently changed source content survives a rejected commit. An I/O failure
or cancellation during commit triggers recovery across updated, created, and
deleted files. Existing source permission bits survive; new files follow the
patch process's inherited umask.

If recovery is incomplete, the error identifies retained backups. Inspect those
paths before retrying. A successful retry requires reviewing the current source
and proposed changes again. The executor does not create or clean up source-side
`.cvw.patch.tmp`, `.orig`, or `.rej` temporary artifacts; unrelated files survive.

## Source selection

`inputs/sot_versions.py::resolve_active_sot_path` owns flat-directory versus
version-pack resolution. Both application operations resolve the requested
source once before reading or compiling their patch. A pack root selects the
directory named by `ACTIVE`; an explicit `versions/<name>` directory stays
pinned regardless of the pack's active version. Flat source directories remain
supported. Root-level source files do not override a pack's selected version.

`cvw project apply` uses the recorded project source unless `--sot-path` is
supplied. `cvw apply` requires that explicit source option. Neither command
falls back to a different configured source. Application owns this decision,
so Python and CLI callers follow the same rule:

- `apply_draft(...)` returns the concrete directory in `ApplyResult.sot_path`.
- `apply_project_patch(...)` returns that directory as a `Path`.
- CLI summaries report this selected directory in their existing `sot_path`
  field, including no-op draft results.

Presence of either `ACTIVE` or `versions` reserves the version-pack layout.
Incomplete packs, unreadable or malformed active selections, missing/non-directory
versions, and active paths escaping the pack's versions directory are errors.
They must not silently select leftover files in the parent directory.

Changing `ACTIVE` after resolution does not retarget an in-flight application;
the next invocation selects again. This pins a directory, not an immutable
source version. Existing expected-text/byte guards still reject observed source
conflicts under the recovery limits below. This does not make version activation
and application a locked transaction.

`tests/ops/test_apply_selection.py` exercises real draft/project application,
explicit overrides, pinned versions, invalid packs, and an active-pointer change
after selection. See [version-pack usage](../howto/sot-versions.md).

## Supported inputs

- `apply_patch_file(patch_path=..., cwd=...)` reads UTF-8 patch bytes once.
- `apply_patch_text(patch_text=..., cwd=...)` accepts a string and executes that
  captured text. It has no separate file argument that can override the text.
- Empty or whitespace-only text performs no writes.
- Ordinary unified diffs require paired file headers and correctly counted
  hunks. Hunk content that resembles a header remains document text. Missing
  final-newline markers are supported.
- Updates use matching old/new paths. Creation uses `/dev/null` as the old path;
  deletion uses it as the new path. New targets must be absent and their parent
  directories must already exist.
- Each target must be a unique regular file or absent destination under the
  selected source directory. Absolute paths, parent traversal, file symlinks,
  directories, duplicate targets, and file renames are rejected.
- Binary/context diffs, arbitrary preambles, and format inference are outside
  this contract. Convert them to an explicit unified diff before application.

Grammar and target checks finish before resolving the external `patch` tool.
The tool runs in unified, noninteractive mode with fuzz disabled; context lines
must match. Both its dry run and real application use the same captured patch
and staged target files. The tool never receives the live source directory as
its working directory.

## Ownership and recovery

`ops/patches.py` captures original target bytes and permission bits, owns the
temporary tool workspace, and maps completed outcomes to shared storage writes
and deletions. Patch-file edits after its read do not change the in-flight patch.
No temporary patch filename is reserved inside the source directory.

`storage.replace_files_atomically` accepts explicit `delete_paths` alongside
replacement payloads. Destinations must be unique across both groups; deletion
targets must be regular files or absent. Deletions preserve recovery copies and
participate in original-byte checks and rollback with replacements. An absent
deletion does not create its parent directory. File-mode overrides apply only
to replacement payloads.

This is recovery for ordinary process errors and cancellation, not writer
locking, simultaneous visibility to readers, or crash durability. Capture is
per input, not an atomic snapshot across all source files. Changes after the
final expected-byte check remain outside the guarantee. External tooling is
trusted; temporary staging is not an operating-system sandbox. Shared storage
limits are in the [bundle recovery contract](configuration-contract.md#build-bundle-recovery).

`tests/ops/test_patches.py` exercises the real patch tool, captured input lifetime,
grammar and target rejection, permissions, and source-write failures.
`tests/test_storage.py` covers grouped deletion/replacement and retained backups
when recovery itself fails.
