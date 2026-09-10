# Project operations

- Start with `docs/reference/project-contract.md#python-ownership` for records,
  identity, manifest, inspection, creation, patch, and guidance owners.
- `__init__.py` exposes callable project APIs. Implement behavior in the
  corresponding owner; internal modules import concrete owners, not this
  entrypoint. Do not import workspace, CLI, or preview presentation here.
- Keep inventory identity separate from executable-project prerequisites and
  review readiness. Preserve retained projects when proposal artifacts expire.
- Use `load_project_summary` for partial inventory descriptions and
  `load_project_details` for validated descriptions and observed proposal
  availability. Missing/invalid proposals become typed issues and unknown fields;
  `load_project` retains execution prerequisites. Metadata
  parsing belongs in `manifest.py`; do not stringify malformed YAML values in
  presentation code or treat recorded digests as proof of current contents.
- Read optional saved guidance through `load_project_plan`; consumers must not
  independently derive and open its path or bypass project ownership checks.
- Use `artifacts.py` for observations of stored job files against recorded hashes.
  Keep those observations separate from inventory, source/plan freshness, and
  run review readiness; do not reread the manifest inside detailed inspection.
- Use `provenance.py` to record and compare the inputs consumed by guidance.
  Read `docs/reference/guidance-provenance.md` before changing the input projection
  or algorithm. Capture fingerprints from consumed values, preserve unknown
  historical provenance, and keep schema/algorithm versions aligned with behavior.
- Validate inputs before artifact writes. Project creation, retargeting, patch
  application, and proposal registration need explicit failure and recovery
  behavior; moving code does not establish transaction safety.
- `patches.py::apply_project_patch` resolves and returns the selected source
  directory before compiling and applying. Route version-pack semantics through
  `inputs/sot_versions.py`; adapters report the operation's returned directory.
  Follow `docs/reference/patch-application.md#source-selection` for authority
  and active-pointer lifetime.
- `patch_authoring.py` owns proposal append validation, locking, and recoverable
  saves. Use `patches.py::read_project_patch_document` for bytes and parsed data
  from one read; keep compilation and source guards in `patches.py`. Follow
  `docs/reference/project-contract.md#proposal-authoring` for preflight, lock
  lifetime, observed edit conflicts, and recovery limits.
- `preparation.py` owns copied source preparation. Nonempty edits require a fresh
  destination outside source/project trees; cleanup must verify directory
  ownership. Preview callers own temporary lifetimes rather than replacing an
  existing staging directory.
- `building.py::build_project` owns project build orchestration. Complete source
  preparation, planning, rendering, and metadata in temporary directories before
  retaining source and outputs as one recoverable group. Preserve source file
  and directory permissions. Use `build/runs.py` for exclusive run allocation
  and cleanup of still-owned empty directories; preserve unrelated artifacts
  and surface any retained inspection path.
  Keep render/content planning in `build/planning.py`, temporary bundle generation
  in `build/artifacts.py`, commit orchestration in `build/pipeline.py`, and terminal
  errors/output in the CLI adapter. Shared file recovery belongs to `storage.py`;
  build code must not import operations for persistence.
- `guidance.py` interprets job evidence and ranks variants. It does not select
  terminal output modes or start preview servers. Catalog loading belongs to
  `cvworkbench.variants`; workspace code owns inventory presentation.
- `workflow.py::guide_project` owns guided creation, preflight, configuration
  capture, and recovery. The CLI presents its result and optionally opens a
  preview. Preserve individual source diagnostics and the original failure when
  cleanup also fails.
- Verify project operation tests, CLI project journeys, and workspace import
  boundaries. Exercise real local files and negative side effects; public
  function imports remain available through `cvworkbench.ops.projects`.
