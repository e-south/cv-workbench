# Project operations

- Start with `docs/reference/project-contract.md#python-ownership` for records,
  identity, manifest, inspection, creation, patch, and guidance owners.
- `__init__.py` exposes callable project APIs. Implement behavior in the
  corresponding owner; internal modules import concrete owners, not this
  entrypoint. Do not import workspace, CLI, or preview presentation here.
- Keep inventory identity separate from executable-project prerequisites and
  review readiness. Preserve retained projects when proposal artifacts expire.
- Validate inputs before artifact writes. Project creation, retargeting, patch
  application, and proposal registration need explicit failure and recovery
  behavior; moving code does not establish transaction safety.
- `guidance.py` interprets job evidence and ranks variants. It does not select
  terminal output modes or start preview servers. Catalog loading belongs to
  `cvworkbench.variants`; workspace code owns inventory presentation.
- Verify project operation tests, CLI project journeys, and workspace import
  boundaries. Exercise real local files and negative side effects; public
  function imports remain available through `cvworkbench.ops.projects`.
