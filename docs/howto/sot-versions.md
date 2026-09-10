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

## Prerequisite: an existing pack

These commands manage an existing pack. `cvw init` creates a flat source directory;
it does not create `versions/base` or `ACTIVE`, and the current CLI has no pack
initialization command. A flat source therefore reports “SoT versions not
initialized” when used with `cvw sot`. Keep that source intact; do not move its
files or create an `ACTIVE` pointer to a nonexistent version just to clear the error.

A pack has this layout:

```text
<pack>/
  ACTIVE                 # contains one version name, such as base
  versions/
    base/                # complete source directory, including declared snippets
    experiment/
```

Pass `--sot-path <pack>` to the commands below when the configured source is a
different directory. A dedicated, non-destructive pack-creation workflow remains
follow-up work; the comparison commands below do not create or migrate a pack.

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

## Comparison contract

`ops/sot_versions.py::diff_versions` compares the two named versions without
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
`tests/ops/test_sot_versions.py` exercise snippet edits/additions/deletions,
inline snippets, unchanged source bytes, path containment, and API/CLI errors.
