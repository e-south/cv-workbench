# Project inspection

- Start with `docs/reference/project-inspection.md` for API and error semantics.
- `inventory.py` owns workspace summaries; `inspection.py` composes full and
  preview observations; `commands.py` describes actions; `guidance.py` explains
  observations. Keep project parsing and mutations in `ops/projects/`.
- Full inspection passes one configuration snapshot through its decision owners.
  Preview inspection retains partial diagnostics without scanning run history.
- Preserve retained history when proposal inputs are unavailable. Describe only
  applicable commands; a retained run can be packaged without live proposals.
- Command descriptions require the selected directory as well as manifest ID.
  Reuse `commands.py` selector ownership; do not replace explicit locations with
  IDs unless the configured mapping selects that directory.
- Keep the public entrypoint explicit and free of implementation. Internal
  modules import concrete owners, never this package's entrypoint.
- Adapters own printing, exit codes, and preview lifecycle. Inspection has no
  writes or terminal output. Do not treat inventory presence, executable
  proposals, saved guidance, artifact observations, and review readiness as
  interchangeable states.
- Verify `uv run pytest tests/workspace tests/cli/test_project_guide.py
  tests/ux/test_preview.py` and the isolated journey in `scripts/verify_repo.py`.
