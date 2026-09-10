# Source-version operations

- Use `docs/howto/sot-versions.md` for initialization and comparison contracts.
- `__init__.py` is the public API. Internal imports use concrete owners:
  `initialization.py`, `lifecycle.py`, `comparison.py`, and `records.py`.
- Keep source selection in `inputs/sot_versions.py`; report the concrete source
  captured by initialization rather than following `ACTIVE` again.
- Initialization requires an explicit source and fresh destination, preserves
  the input/configuration, and validates captured bytes before destination writes.
  Reuse `storage.replace_files_atomically` for recoverable creation; do not add
  a separate directory-replacement or cleanup mechanism.
- Comparison remains read-only and reports expected failures through
  `SotPackError`; its evidence is not full source-schema validation.
- Exercise `tests/ops/sot_versions/`, source CLI tests, and source-selection tests.
  All creation, activation, failure injection, and cleanup checks use disposable
  source trees. Never convert the live private source as a test or migration shortcut.
