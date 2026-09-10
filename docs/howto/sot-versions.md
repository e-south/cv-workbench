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
Each version lives under `<pack>/versions/<name>/`, with `<pack>/ACTIVE` selecting
the current version. The examples create a separate `local/source-versions` pack.

## Create a pack

`cvw init` prepares a workspace with a flat source directory. Create a separate
version pack from an explicitly selected source:

```bash
uv run cvw sot init --source ./sot.sample --destination ./local/source-versions --json
```

Replace `./sot.sample` with your private source path for personal work. The
destination must not exist. The default initial version is `base`; use `--name`
to choose another name. Version names must be a single nonblank path component,
without leading/trailing whitespace or control characters. The command returns
the concrete source copied, pack root, active name, and version directory.
It preserves the original source and
workspace configuration. Use the returned pack path explicitly in subsequent
commands until you deliberately change your configured source.

A pack has this layout:

```text
<pack>/
  ACTIVE                 # contains one version name, such as base
  versions/
    base/                # complete source directory, including declared snippets
    experiment/
```

The source can be a flat directory, a pack (its active version is copied), or an
explicit version directory. Pack selection is resolved once and reported; a later
`ACTIVE` edit does not retarget an in-flight copy. When your configured source
already points at this pack, the `--sot-path` flags below may be omitted.

When applying an edit, pass the pack root to select `ACTIVE`, or pass a concrete
`versions/<name>` directory to keep that edit pinned. The command reports the
directory it edited. See the [application selection contract](../reference/patch-application.md#source-selection)
for project defaults, invalid-pack errors, and in-flight selection behavior.

## List versions

```bash
uv run cvw sot list --sot-path ./local/source-versions
```

With `--json`, `sot.list` returns `data.root`, `data.active`, and a `data.versions`
array. Each version name is preserved as one string, including names containing
commas. Plain/default output keeps the human-readable joined list. Automation
should consume the array rather than splitting terminal text.

## Create a new version

```bash
uv run cvw sot new experiment --from base --sot-path ./local/source-versions
```

If `--from` is omitted, the active version is used as the base.
An explicit `--from` selects that version independently of `ACTIVE`.

## Activate a version

```bash
uv run cvw sot activate experiment --sot-path ./local/source-versions
```

## Repair a selection

An empty, malformed, missing, or stale `ACTIVE` record does not prevent an
explicitly named activation:

```bash
uv run cvw sot activate base --sot-path ./local/source-versions
```

Choose an existing version name. Activation replaces the damaged regular record
or creates a missing record with mode `0600`; it preserves source contents and
configuration. Named comparisons and `sot new --from <version>` also work while
selection is damaged. Building from the pack, applying to its active source, and cloning
without `--from` continue to require a valid selection.

The pack must already contain an actual `versions` directory. A flat source is
not converted by activation. Linked selection files and linked version-container
directories are rejected. Repair those filesystem entries explicitly before
continuing; operations do not follow them to foreign targets.

The [configuration contract](../reference/configuration-contract.md#source-references-and-active-selection)
distinguishes the chosen source location from its selected active version.

## Diff versions

```bash
uv run cvw sot diff base experiment --sot-path ./local/source-versions
```

Diffs normalize YAML keys to keep output stable and readable.

To build from the active experiment:

```bash
uv run cvw build --sot-path ./local/source-versions --variant cover-letter --format md,pdf,docx
```

## Initialization contract

The public Python API is `cvworkbench.ops.sot_versions.initialize_pack`, with
keyword arguments `source`, `destination`, and optional `name`. Its
`InitializedSotPack` result exposes `source`, `root`, `active`, and `version`.
The implementation owner is `ops/sot_versions/initialization.py`.

Initialization checks for required source files before reading the directory's
other contents. It captures the selected source's regular files, empty directories,
bytes, and permission bits. Symbolic links and special files inside that source
are rejected. It validates a private temporary copy using the existing source
schema owner and checks the original content/inventory again before destination
writes. Invalid data, overlapping/existing destinations, and observed source
changes stop creation. Diagnostics do not echo invalid YAML values.

Pack and `versions` directories use mode `0700`; `ACTIVE` uses `0600`. Copied
content retains its original permission bits beneath the private pack root.
The shared recoverable file writer creates the new tree and writes `ACTIVE`
last. Failure/cancellation cleanup follows the
[file recovery contract](../reference/configuration-contract.md#build-bundle-recovery);
it does not claim simultaneous visibility, source locking, or crash durability.
The command must finish successfully before other operations use the new pack.
Original source timestamps are not copied, and no settings are retargeted.

`tests/ops/sot_versions/test_initialization.py` covers CLI/API creation, active
and pinned sources, source/configuration preservation, destination conflicts,
source changes, private validation copies, and interrupted-write recovery.

## Lifecycle contract

The public `cvworkbench.ops.sot_versions` API exposes `list_versions(root)`,
`create_version(root, name, base)`, and `activate_version(root, name)`. Lifecycle
operations belong to `ops/sot_versions/lifecycle.py`. Input-owned
`validate_version_name` owns name constraints for commands and selection records;
`read_active_version` rejects linked, malformed, or unreadable selection records;
`resolve_version_directory` confines named directories to the pack's `versions`
directory and is shared by active selection, lifecycle, and comparison.

Cloning requires an absent destination. It reuses `ops/sot_versions/copying.py`
with initialization to capture regular file bytes, ordinary permissions, and
empty directories. Linked/special source entries and observed changes during
capture reject the clone before destination writes. Existing destination files,
directories, and dangling links are preserved. Cloning keeps `ACTIVE` unchanged.
It preserves an in-progress source without requiring full schema validation;
source timestamps are not copied. Validate/build the selected source separately.

Activation requires an existing version directory inside the pack and a regular
or absent `ACTIVE` file. It captures prior selection bytes (or absence) and uses
expected-content
checks before and after staging. An observed competing selection edit is
preserved and reported as an error. Cloning and activation use the shared
[file recovery contract](../reference/configuration-contract.md#build-bundle-recovery):
injected copy/replacement failures and cancellation restore the prior selection
or remove the partial new version. Recovery failures retain the writer's explicit
diagnostic/backup behavior. Ordinary I/O failures become `SotPackError`; expected
input errors remain `SotVersionError`. CLI adapters print errors on stderr and
exit 1; cancellation is propagated after cleanup.

These checks do not lock source directories or exclude all concurrent writers,
provide simultaneous visibility of a copied tree, or establish crash durability.
Wait for a successful command result before using its output.
`tests/ops/sot_versions/test_lifecycle.py` covers API/CLI boundaries, partial-write
recovery, permissions, empty directories, and observed concurrent changes.
`tests/cli/test_sot.py` exercises explicit/configured pack recovery while document
consumers still reject damaged selections and cloning without an explicit base
remains strict.

## Comparison contract

`ops/sot_versions/comparison.py::diff_versions` compares the two named versions without
changing either version or `ACTIVE`. It includes required/present optional YAML
files and the union of file snippets declared by either version's `snippets.yaml`.
The on-disk snippet document contains a top-level `snippets` list. Inline snippets
are compared through that YAML file; file snippets are compared by their relative
paths. Added or missing files produce additions or deletions. Whitespace at the
ends of text files and YAML key ordering are normalized.

Named version directories must stay inside the pack's `versions` directory.
Source files and declared snippets must stay inside the corresponding version;
absolute/traversing snippet paths and symlinks escaping that version are rejected
before their content is read. Malformed YAML, invalid UTF-8, or unreadable files
raise `SotPackError`; the CLI prints an error and exits 1 without echoing YAML
values. This is a read-only comparison, not whole-source schema validation or
a concurrent-writer snapshot. Stable-path checks do not lock filesystem names.

Use `--json` for the command's machine-readable result: `command: sot.diff` and
`data` containing `root`, `left`, `right`, and the unified `diff` string. Identical
versions return an empty `diff`; successful comparisons exit 0 whether changed
or unchanged. Plain/default output retains the unified diff or “No differences
found.” Errors exit 1 and report diagnostics on stderr. Tests in
`tests/ops/sot_versions/test_comparison.py` exercise snippet edits/additions/deletions,
inline snippets, unchanged source bytes, path containment, and API/CLI errors.
