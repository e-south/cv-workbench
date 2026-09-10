# Authored publication ownership

- Start with [the lifecycle contract](../../../../docs/reference/publication-contract.md).
- `pdf.py` owns sanitization and layout correspondence; `policy.py` owns disclosure policy loading; `manifest.py` owns authored provenance schemas/serialization; `artifact.py` owns manifest eligibility and immutable artifact reads.
- `object_text.py` decodes PDF object strings for the shared disclosure checks;
  see [non-page disclosure](../../../../docs/reference/publication-contract.md#non-page-disclosure).
  Keep object decoding separate from policy decisions and page redaction.
- `record.py` owns private snapshot schemas; `state.py` owns freshness and review declarations; `packet.py` renders the local visual evidence.
- `inputs.py` captures the five preparation files into private temporary copies;
  `pdf.py` processes those copies. `record.py::PreparationInputs` retains the
  original file identities and captured-byte hashes, and serialization checks
  their current bytes before output replacement. See the lifecycle contract's
  [input lifetime](../../../../docs/reference/publication-contract.md#input-lifetime).
- Preparation and sync capture or reuse one `ConfigSnapshot`. CLI selection
  must pass the same snapshot into the operation instead of reopening its path.
- CLI adapters live in `cli/commands/publication.py`; workflow descriptions live in `workspace/publication.py`. Neither may weaken the operations checks.
- Keep private preparation and review records out of sanitized site manifests. Validate freshness and review before site writes in `ops/syncing.py`.
- Bind signature, digest, disclosure checks, and review to the same captured PDF bytes. Copy plans carry bytes; they must not reopen source paths when applying writes.
- Test changes through `tests/ops/publication`, `tests/ops/test_sync.py`, and `tests/cli/test_publication.py`, including stale inputs, wrong hashes and partial writes.
