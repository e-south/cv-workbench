# Test workspace ownership

- Read [the verification contract](../docs/reference/verify-contract.md#test-workspaces)
  before changing test setup or running repository-wide checks.
- `conftest.py` provides an empty temporary working directory for every test.
  Request `sample_workspace` when a test needs populated sample inputs.
- Put custom inputs and outputs beneath `tmp_path` or the requested workspace.
  Resolve checked-in fixtures from `__file__` for reads; do not write to checkout
  inputs, `local/`, or `var/` through repository-root paths.
- Preserve negative-path intent: missing fixture data must not substitute for the
  configuration, validation, or runtime failure a test intends to exercise.
- Run the workspace-isolation regression when changing fixtures or CLI test paths,
  then run the full suite. Keep subprocess output available for failed checks.
