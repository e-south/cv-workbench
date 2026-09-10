# Content review operations

- Start with `docs/reference/project-contract.md` for review/import semantics and
  `docs/reference/artifact-retention.md` for run dependencies.
- `packs.py` owns review bundle creation; `importing.py` owns DOCX conversion and
  import-draft writes; `patches.py` interprets edits without owning CLI or bundle
  writes; `targets.py` resolves run/project inputs; `catalog.py` inspects bundles.
- Keep authored publication review in `ops/publication/`. A content review edits
  source claims; a publication review approves one prepared public PDF.
- Validate run identity and required inputs before writing or replacing a bundle.
  Never reinterpret an edited document against an implicit newer build.
- Test review/import behavior through the operation or CLI with deterministic
  fixtures; use an actual DOCX conversion for end-to-end journeys.
