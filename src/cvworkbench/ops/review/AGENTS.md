# Content review operations

- Start with `docs/reference/review-contract.md` for review/import semantics and
  `docs/reference/artifact-retention.md` for run dependencies.
- `packs.py` owns review bundle creation; `importing.py` owns DOCX conversion and
  import-draft writes; `patches.py` interprets edits without owning CLI or bundle
  writes; `targets.py` resolves run/project inputs; `catalog.py` inspects bundles.
- `record.py` owns source identity and baseline hashes. A valid record pins its
  run for imports and for GC within the configured review store. Do not infer
  missing provenance from whichever run happens to be latest.
- Keep authored publication review in `ops/publication/`. A content review edits
  source claims; a publication review approves one prepared public PDF.
- Validate run identity and required inputs before writing or replacing a bundle.
  Bundle selection uses retained run artifacts; only import target resolution
  requires current source and proposal inputs. Keep these prerequisites separate.
  Never reinterpret an edited document against an implicit newer build.
- Test review/import behavior through the operation or CLI with deterministic
  fixtures; use an actual DOCX conversion for end-to-end journeys.
