# Command adapters

- Start with `docs/concepts/architecture.md#command-adapters` for ownership;
  use the matching reference contract for behavior and output semantics.
- `cli/app.py` registers commands and groups. Keep implementations in the
  corresponding command family here; owners must not import the entrypoint.
- Adapters own option parsing, terminal presentation, and exception translation.
  Workspace inspection and operations remain the programmatic workflow owners.
- `documents/` separates build/render, comparison, and content-review commands.
  `projects/` separates workflow entry points, guidance, patch authoring, and
  presentation. Publication remains its own command family.
- Preserve command names, flags, help, output modes, and error behavior during
  extraction. Public command changes need explicit contract changes and tests.
- Shared CLI mechanics live in `cli/helpers.py` and `cli/output.py`; domain
  decisions do not belong in a shared helper module.
- Verify with `uv run pytest tests/cli tests/workspace` and the operation tests
  for the affected command family. Use real isolated journeys for workflow
  behavior; adapter dispatch/presentation tests alone do not establish it.
