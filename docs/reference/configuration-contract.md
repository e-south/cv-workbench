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
creating its destination directory. Rendering/tool failures after preflight
retain their existing artifact/error behavior. Project CLI setup may create its
project-local source/run workspace before the build pipeline is entered.

Each build run and dist manifest records `configuration.sha256`, identifying
the workbench config bytes used by that build. It remains the captured hash if
the file is edited during rendering; the manifest does not re-read the config.

## Scope and adoption

This snapshot covers `workbench.yaml`, not a transaction across every input
file or directory. Source facts, active-version pointers, variant files, theme
assets, publication policy, and site configuration have separate lifetimes.
Their existing hashes/checks do not establish a global immutable input bundle.

Workspace inspection, publication/lifecycle orchestration, and preview
controller selection still include path-based resolution outside the captured
build boundary. Adopt explicit snapshots at those operation boundaries with
their own behavior tests. Do not infer that accepting `ConfigSource` alone
proves a whole caller uses one generation.

Verification:

```bash
uv run pytest tests/ops/test_config.py tests/build/test_configuration.py
uv run pytest tests/build
```
