---
id: reference-configuration-contract
intent: Define configuration lifetime, resolution, and build preflight guarantees.
audience: [operator, agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Configuration contract

`config.py` owns workbench configuration loading and path/settings resolution.
The canonical example is [config/workbench.yaml](../../config/workbench.yaml).
Source facts, variant definitions, themes, publication policy, and destination
configuration retain their separate owners.

## Configuration lifetime

```python
from pathlib import Path
from cvworkbench.config import read_config, resolve_dist_path

configuration = read_config(Path("config/workbench.yaml"))
destination = resolve_dist_path(configuration)
print(configuration.sha256)
```

`read_config` reads a file once into `ConfigSnapshot`: the resolved absolute
path, immutable original bytes, deeply immutable parsed values, and the
SHA-256 of those original bytes. Mapping values cannot be assigned, sequences
are tuples, and YAML sets are frozen sets. Recursive YAML values are rejected.
The bytes and parsed values are excluded from the snapshot's representation.
Shared YAML aliases retain shared container identity, so capture does not
expand a compact alias graph into duplicated subtrees. Mutable payload exports
preserve that sharing within each independent payload.

Resolvers accept a `Path` or an explicit `ConfigSnapshot` (`ConfigSource`). A
path captures current file contents when a value is requested. Passing the
same snapshot through one operation gives that operation coherent settings,
even if the file changes or is removed after capture. A subsequent operation
captures fresh contents. There is no implicit process-wide cache.

`load_config` returns an independent mutable dictionary for consumers that need
a payload. Changes to that dictionary do not update a snapshot or persist to
the configuration file. Direct snapshot construction requires immutable bytes
and an absolute path; ordinary callers use `read_config`.

## Resolution and errors

Relative workbench config paths resolve from the current directory or its
parents. Paths declared inside the workbench config resolve relative to the
config's directory. Workspace-owned defaults use the workspace's `var/` root.

Omitted or null artifact-path settings use their declared defaults. An explicit
artifact path must be a nonempty string; booleans, numbers, and containers are
errors. `variant_lifecycle.ttl_days` must be a positive integer; `true` does not
mean one day. Missing fields required by a particular operation remain explicit
errors. Loading an empty config does not invent missing required settings.
The configured source path must be a nonempty string. Optional `pdf_engine`
and `style_preset` render settings may be omitted or null; explicit values must
be nonempty strings.

Unreadable configuration raises a filesystem error. Invalid UTF-8, malformed
YAML, a non-mapping document, recursive values, and invalid requested settings
raise `ValueError`. Encoding/YAML errors identify the config file without
echoing its contents.

## Build and render boundaries

The `build` and `render` CLI adapters capture one workbench snapshot before
selecting configured inputs or render settings. `build_documents` also accepts
an explicit snapshot and captures one when called with a path. It reuses that
snapshot for default variant, run/output roots, theme, preset, and PDF engine.

Build preflight resolves destinations, filters, themes, and all requested
format plans before the pipeline creates its run or output artifacts. Invalid
theme/style/path configuration therefore cannot leave a partial build behind.
The standalone render command validates its settings and format plans before
creating its destination directory. Project builds use the
[project build operation](project-contract.md#project-build-api) to validate
temporary source preparation and complete build planning before allocating a
persistent project run.

`build/planning.py::plan_build` performs no artifact writes and returns a
request-local `BuildPlan` containing selected content, normalized formats,
captured configuration, input fingerprints, and resolved render choices.
Private content is omitted from its representation.
`build/pipeline.py::execute_build` stages and commits the plan's artifacts;
`build_documents` composes the two. Full source-schema validation remains the
responsibility of the CLI/preview or project operation before this lower-level
pipeline. Planning performs source loading and content selection, not a separate
schema-validation policy.

`inputs/sot.py::load_sot_snapshot` owns source parsing and fingerprints. Each
required or present optional YAML file is read into bytes once, then parsed and
hashed from that same content. File snippets are captured once per declared path;
their text normalizes line endings and trims surrounding whitespace, while their
hashes identify the original bytes. Inline snippet hashes identify the original
parsed text encoded as UTF-8, including surrounding whitespace.
`variants.py::load_variant_snapshot` likewise parses and hashes one captured
variant definition. `load_sot` and `load_variant` return their ordinary parsed
payloads through these same owners.

The plan carries these fingerprints to `build/manifest.py`; manifest collection
does not reopen source YAML, snippets, or the variant. Editing or removing those
files after planning cannot alter the plan's content or recorded input hashes.
Adding an optional source file after planning does not report it as consumed.
The `sot_hashes`, `snippet_hashes`, and `variant_hash` fields retain their existing
names and SHA-256 encodings. Resume and rendered-output hashes describe generated
artifacts and are collected during execution.

A plan is not a durable job specification, publication approval, or deeply
immutable input bundle. Source snapshot hash mappings are read-only, but parsed
source payloads and nested plan values remain ordinary Python containers; callers
must not mutate them between planning and execution. Capture is per input, not an
atomic filesystem snapshot across all files. Filter and theme assets must remain
available and unchanged during rendering. A project operation retains its prepared
source before execution and updates the plan's source location without reparsing
its selected content. Explicit render-asset lifetimes are enforced below;
durable dependency snapshots remain a separate contract.

Each build run and dist manifest records `configuration.sha256`, identifying
the workbench config bytes used by that build. It remains the captured hash if
the file is edited during rendering; the manifest does not re-read the config.

### Render asset lifetime

`build/assets.py::capture_render_assets` records the explicit file dependencies
of a build plan. Its `RenderAssetContract` keeps immutable fingerprints and the
ordered selected filter paths. The contract covers `theme.yaml`, every declared
route's defaults/templates used by the composite theme hash, and styles selected
for the requested formats. `themes.py::theme_hash_paths` owns composite-hash
membership and ordering; unselected routes remain part of that theme identity.

`Theme.definition_sha256` identifies the bytes parsed for the theme definition.
Planning rejects a definition edited after parsing, differing hashes observed
while preparing format plans, or a style inconsistent with its recorded hash.
The resulting `BuildPlan.theme_hash` uses the recorded fingerprints rather than
another filesystem read. Composite theme and style hash encodings are unchanged.

Execution checks recorded assets before allocating outputs and again after
staged rendering/metadata completes. Missing, unreadable, or changed assets fail
with `RenderAssetError` (a `ValueError`) before the bundle commits. Changes to the
selected filters or introduction of unrecorded render paths also fail. The CLI
and preview use their existing error handling; a previous bundle survives.

Build manifests additionally record `render.filters`, an ordered list of
`name`/`sha256` entries for selected Lua filters, without absolute filter paths.
An empty list records that no filters were selected. Historical manifests without
this field have unknown filter provenance; do not infer it from current files.
The renderer treats `filter_paths=None` as discovery of the known built-in files,
an empty sequence as no filters, and a supplied sequence as the exact selection.
A planned empty selection does not pick up files added afterward.

`BuildPlan.pdf_engine` is the effective engine of the selected PDF route, or
`None` when PDF is not requested. Theme overrides therefore agree with manifest
tool metadata, and Markdown, HTML, DOCX, and ATS builds do not probe an unused
configured PDF engine. Workbench configuration still undergoes its ordinary
field validation.

These are observed lifetime checks, not retained asset bytes or a locked
filesystem snapshot. Transient edits reverted between checks can go undetected,
and another writer can change a file after the final check. Indirect reads from
Pandoc defaults, template partials, Lua modules, fonts, user data, or external
processes are not a captured dependency graph. Assets remain trusted execution
inputs. Full reproducible asset packs need an explicit dependency contract;
this change preserves existing path resolution and does not relocate assets.

The negative-path and real-render checks live in
`tests/build/test_render_assets.py`; effective-engine behavior is covered by
`tests/build/test_manifest.py`.

### Build bundle recovery

`build/artifacts.py` defines bundle membership and materializes documents,
styles, selections, resume data, and manifests in temporary directories.
`build/pipeline.py` owns destination preflight, temporary lifetime, and the final
recoverable write through `storage.replace_files_atomically`. `build/runs.py`
owns exclusive run allocation and failure cleanup for ordinary and project builds.
Storage is a lower-level owner shared by builds and operations; it does not import
either workflow layer or command/preview adapters.

Each artifact has an explicit run/dist location and semantic role. Overlapping
roles (for example, rendered `canonical.md` over canonical input) fail before
output writes. Shared run/dist directories, including directory aliases, retain
one run manifest with `created_at`. Audited retained HTML runs carry their linked
CSS as well as the document. Unselected formats and unrelated files are preserved.
An unaudited pipeline call updates only its selected documents, canonical input,
and styles; preexisting audit metadata is not refreshed by that mode. Ordinary
preview routes these writes to [separate preview directories](preview-contract.md#artifact-ownership)
so its output cannot invalidate an audited build.

Rendering and metadata collection finish before persistent artifacts change.
The collector receives captured resume bytes, so an abandoned metadata task does
not reopen temporary files after a render failure releases them. Build failures
return without waiting for that task to finish. Default run allocation occurs
only after the completed payloads have been captured; explicit run directories
remain caller-owned. The [project build operation](project-contract.md#project-build-api)
uses a temporary run for this call and retains its completed documents and
prepared source together afterward.

Existing destination bytes are captured before rendering and checked again
before and after replacement staging. Observed edits fail closed. Final writes
replace regular files or absent destinations; file symlinks and directories are
rejected. Storage rejects duplicate resolved destinations and stages replacement
payloads beside their targets while preserving existing permission bits. The
pipeline orders manifest writes after documents. Storage restores the complete
attempted group after an I/O failure or cancellation. An interrupted call keeps its original exception type.
If restoration fails, recovery copies remain and the error reports incomplete
rollback. CLI builds report storage failures as errors; preview retains its
previous build id/document and records the error.

Source patch application adds explicit deletions to the same storage group;
see the [patch application contract](patch-application.md#ownership-and-recovery)
for target checks, deletion recovery, and source permissions.

Storage optionally accepts `new_directories`, a mapping of absent directories to
permission bits. Entries must be unique, have valid modes, and not collide with
file destinations; existing directories and symbolic links are rejected. New
directories begin owner-only while files are staged, then receive their recorded
modes after file replacement. Empty directories are retained too. If mode
application fails, recovery restores access to still-owned new directories before
recovering files and removing empty directories. Existing directory modes are
never changed by this option. Project retention uses this contract to preserve
source permissions without widening private subdirectories.

Failure cleanup removes only empty directories created by the operation whose
device/inode identities still match. Nonempty directories, replacement
directories, recovery copies, and caller-owned files survive. A failed default
run and newly created parents are removed when still owned and empty; otherwise
retention is reported in notes attached to the original error. Build CLI errors
print those notes on stderr, including the retained inspection path.

This is recoverable replacement across files, not simultaneous visibility for
concurrent readers, writer locking, or crash durability. Readers can observe the
replacement sequence, and edits after the final byte check remain outside the
guarantee. Forced termination and repeated interruption during recovery can
prevent rollback. Templates, defaults, and filters remain trusted execution
inputs; temporary staging does not sandbox their external side effects. See
`tests/build/test_bundle_recovery.py` and `tests/test_storage.py` for real-render
and filesystem failure checks.

### Render output recovery

`render_document` delegates to `render_documents`, which owns staging and output
promotion for single, sequential, and parallel rendering. Requests must have
distinct resolved output paths; duplicates and path aliases are rejected before
creating output directories. Each render writes inside a temporary directory
beneath its destination's parent, retaining the requested filename and extension.
That directory is private to the render operation. A successful output replaces
its destination atomically before its success callback runs.

Outputs are promoted in request order. If rendering, promotion, or a callback
raises, already promoted outputs remain and unpromoted outputs retain their
previous contents or stay absent. Temporary outputs are removed after dispatched
workers finish, including when a callback raises `KeyboardInterrupt`. A caller
cannot infer that the whole batch succeeded from the first callback.

This is an individual-output guarantee for direct renderer callers. Parent
directories can remain after failure. Builds add the bundle recovery boundary
above; direct `render` calls do not. Interruption of external processes and
recovery after forced process termination are not provided by either contract.

## Variant and artifact names

`variants.py` owns variant identity and output filename validation. Variant IDs
start with an ASCII letter or number and contain only ASCII letters, numbers,
dots, underscores, or hyphens. Selectors such as `--variant` and promotion IDs
follow this same contract. They select a file beneath `config/variants/`; an ID
is not a path.

`load_variant(path)` uses `load_variant_snapshot(path)`, which reads YAML bytes
once and delegates to `parse_variant(raw)`. Project
creation and retargeting use that same parser to validate the exact parsed
definition they will copy. This avoids a separate project-only schema and a
second variant-file read between validation and serialization.

`variant.output_name` is a filename stem, such as `cv` or `Example Person CV`.
Omitted/null values use `cv`. Explicit values must be nonempty strings; path
separators, control characters, reserved filename punctuation (`<>:"|?*`), and
the components `.` and `..` are rejected. Human-readable spaces and Unicode
letters are retained. Both YAML loading and direct `Variant` construction
enforce these name contracts.

`build.paths.output_path` requires an ASCII alphanumeric format extension before
joining the generated filename to its selected destination. Build/render reject
unsafe names before creating artifacts; manifests can therefore refer to the
actual generated filename within that destination. Configured output roots and
explicit destination overrides retain their existing ownership semantics.

## Inspection boundaries

`inspect_workspace` captures one snapshot for the source selection, default
variant, retention setting, run/project/review locations, and publication
inventory. The `context`, `bootstrap`, and `workflow` commands share this API.
`inspect_status` and its `status` command capture the same settings boundary
while requiring a valid selected source. Python callers may supply an existing
snapshot to either inspector. Editing or removing the
workbench file after capture does not change that inspection's settings; the
next path-based invocation reads current contents.

`inspect_project` shares one captured configuration across project resolution,
latest-run lookup, proposal-ID suggestions, and saved-guidance comparisons.
Its `project show` adapter owns terminal error translation. Preview observation
inspection can consume that same explicit snapshot without acquiring run or
command state. See the [project inspection contract](project-inspection.md).

`inspect_publication` likewise captures or reuses a snapshot for publication,
review, and person-source locations. It retains its explicit freshness and
review checks. Workflow descriptions receive the resolved workspace location
and ordinary config path; constructing commands does not reopen the settings.

## Project guidance

`ops.projects.guide_project` captures one configuration generation for source and
default selection, creation, retargeting, proposal registration, and failure
cleanup. It also accepts an explicit snapshot. File-based and URL-based project
creation preserve a provided snapshot instead of reopening its path. Registry
registration/discard helpers accept that captured configuration throughout the
guided operation.

An edit or removal of `workbench.yaml` during guidance does not switch project
locations or registry settings. The result's ordinary config path supports later
commands, which independently select settings. Job/source/variant file reads and
multi-file artifact mutations have their own lifetimes; see the
[guidance API](project-contract.md#guidance-api) for preflight and recovery limits.

## Scope and adoption

This snapshot covers `workbench.yaml`, not a transaction across every input
file or directory. Source facts, active-version pointers, variant files, theme
assets, publication policy, and site configuration have separate lifetimes.
Their existing hashes/checks do not establish a global immutable input bundle.

Other project command orchestration, publication preparation/sync, lifecycle
mutations, and preview controller selection still include path-based resolution
outside the captured boundaries. Adopt explicit snapshots at those operation
boundaries with their own behavior tests. Do not infer that accepting
`ConfigSource` alone proves a whole caller uses one generation.

Verification:

```bash
uv run pytest tests/ops/test_config.py tests/build/test_configuration.py
uv run pytest tests/build
uv run pytest tests/workspace tests/ops/publication/test_state.py
uv run pytest tests/ops/test_project_guide.py
```
