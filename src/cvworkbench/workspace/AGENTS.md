# Workspace inspection and guidance

- Start with `docs/reference/context-contract.md` for payload and recipe semantics;
  use `docs/concepts/architecture.md` for import direction and owner routing.
- Keep inspection read-only and terminal-independent. Raise domain exceptions;
  CLI adapters own output modes, error messages, and exit codes.
- Source, variant, run, project, review, and publication inventories each have
  their own module. `context.py` composes them; it does not own artifact mutation.
- Workflow descriptions live by intent under `workflows/`. Keep recipe IDs,
  ordering, placeholder handling, and config/source propagation stable.
- Project inventory, inspection, command descriptions, and guidance live under
  `projects/`; read its scoped `AGENTS.md` before extending those owners.
- Commands are descriptions only. Build, import, apply, cleanup, and publication
  writes remain in their existing `build/` or `ops/` owners.
- Workspace code must not import `cli`, `dev`, `typer`, or `rich`. Lower-level
  operations must not import workspace inspection. Verify with
  `uv run pytest tests/workspace tests/cli/test_context.py tests/cli/test_status.py`.
