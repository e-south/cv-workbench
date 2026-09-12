---
id: reference-review-contract
intent: Define content-review provenance, import selection, and source-retention contracts.
audience: [operator, agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Content Review

A content review edits a generated CV, resume, or cover letter against one
specific build run. It is separate from
[publication review](publication-contract.md), which records inspection of a
prepared public PDF.

Review conversion selects the ATX-heading option advertised by the installed
Pandoc: `--markdown-headings=atx` on current versions, or the older
`--atx-headers` spelling where supported. It fails before conversion when neither
option is available; a failed conversion never falls back to unverified text.

## Review and Import

```bash
cvw reviewpack --run <run-id> --json
# Edit the DOCX path returned by reviewpack.
cvw import-docx --from <review-docx> --json
```

`reviewpack` can select a run explicitly or select the latest run for a variant
or project. The resulting bundle records that exact selection. It copies the
run's DOCX and PDF, creates a checklist, and writes `review-source.json` with
owner-only permissions. Source artifacts must include `canonical.md`,
`selection.json`, and `manifest.json`. The returned `source_record` path makes
the relationship inspectable without guessing a directory layout.

By default, variant bundles live at `var/reviews/<variant>/` and project bundles
at `var/reviews/projects/<project>/`, beneath the configured reviews root.
Output filenames follow the selected run's manifest; they need not be `cv.*`.
Checklists include selected resume bullets or cover-letter sections from the
retained run's [selection evidence](selection-contract.md), without reselecting
from current source files.

Packaging reads the selected run's artifacts without requiring current source,
configured variant definitions, or live proposal files. An explicit `--project`
requires valid manifest identity and constrains the run to that project.
With `--run`, project ownership comes from the run's project-scoped ID; a missing
current project does not move its bundle into the variant review directory.
Run variant and project identifiers are validated before deriving a destination.
This allows reviewing retained artifacts after proposal discard or expiration.

Keep `review-source.json` beside the edited DOCX. Import uses its source run even
when newer builds exist. An optional `--variant` or `--project` constrains that
selection. An explicit `--run` must agree with the recorded source. Relative
project-run paths preserve their full project-scoped identity.

For a standalone DOCX or a historical bundle without a source record, import
requires an explicit `--run`. It does not infer a baseline from the newest
variant/project build. Copying a DOCX elsewhere without its record therefore
requires naming the baseline deliberately.

Import constructs a patch against current source inputs and therefore retains
stricter prerequisites. A project-scoped source run requires its current project,
proposal variant, and patch. Missing project inputs fail before DOCX conversion
or draft writes; import does not reinterpret the run as a configured variant.
The current project manifest identity must match the selected run's project ID.
Restore those inputs before importing edits. Packaging availability alone does
not establish import or application readiness.

## Provenance and Health

The strict version-1 source record identifies the run by ID and absolute local
path, names the review outputs, and records SHA-256 hashes of the canonical
text, selection metadata, run manifest, and original DOCX/PDF outputs. It rejects
unknown fields, malformed versions, unsafe relative paths, and missing baseline
or output identities.

Import validates those source artifacts before conversion or draft writes.
Canonical bytes are captured once for interpretation and the recorded hash;
changes during conversion fail before draft allocation. Draft payloads commit
through one recoverable file transaction. A failed commit removes its empty owned
directory while preserving prior drafts and any unexpected recovery evidence.
Editing the review copy is expected; editing its immutable source run invalidates
the baseline. These hashes establish identity since bundle creation, not a
human review decision or proof that current SoT files still match the build.
Supported patches separately enforce the
[compare-and-set source contract](project-contract.md#patch-format).
Applying an eligible draft also uses the shared
[patch application contract](patch-application.md) for staged execution and
recovery across source-file changes.

`context` and `status` expose a review's `source` object with its run, record
path, filenames, issues, and one of these states:

| State | Meaning |
| --- | --- |
| `ready` | Recorded source artifacts still match; this is not review approval |
| `changed` | A source artifact's hash differs |
| `missing` | A source artifact is absent |
| `invalid` | The record or its path contract cannot be validated |
| `untracked` | No source record exists; import requires an explicit run |

## Retention and Replacement

Run GC retains sources referenced by records beneath the configured reviews
root, including runs whose manifests are damaged. `keep_reasons` names the
protecting review. A malformed record stops GC before deletion because its
dependencies cannot be established. Historical bundles without records and
Python callers' custom bundles outside the configured store require explicit
`--keep` retention. Standalone imports retain their declared canonical source
through the [import-draft retention contract](artifact-retention.md#import-draft-dependencies),
including no-op drafts. Retention does not establish source freshness or approval.

`reviewpack --force` explicitly replaces an existing review, including its
edited DOCX. Required inputs and selection metadata are checked first. The
DOCX, PDF, checklist, and source record are replaced together through the
recoverable file transaction; a failed replacement restores previous files.
If filesystem rollback also fails, the error identifies retained recovery
backups. Superseded extra files are pruned only after the replacement succeeds.
Targets that overlap the source run or would replace the reviews store are
rejected before writing.

## Import Outputs

Each import creates `var/drafts/import-*/draft.json`, the authoritative
`apply_status` record, plus the imported Markdown and informational `notes.md`.
Supported Experience bullet and Projects summary edits become `project-ops`
in `patch.yaml`. Formatting-only normalized edits report `ready_no_changes`.
Unsupported edits produce `patch.diff` and `review_diff_only`; they are not
silently applied to SoT. Follow the reported status before applying a draft.

## Markdown comparison

Review conversion and syntax normalization belong to `ops/review/markdown.py`.
The canonical Markdown and imported DOCX text are normalized with the
same local Pandoc Markdown writer before supported-edit comparison. ATX headings
and unwrapped lines prevent writer defaults from changing the parser's section
boundaries. The writer also normalizes equivalent link notation; visible labels
and destinations remain part of the comparison. No source content is rewritten
by normalization, and a fallback `patch.diff` retains the original canonical
and imported text for inspection.

The existing supported-edit rules still apply. A real reviewed experience
bullet can produce `ready` with its stable target and expected old text; an
unchanged document produces `ready_no_changes`. A changed contact-link
destination remains `review_diff_only`. This is syntax normalization, not a
general promise to reconstruct arbitrary Word edits or accept changed claims
outside the supported fields.

Conversion and comparison finish before an import draft directory is created.
Pandoc/normalization failures leave the draft inventory unchanged. Later file
writes retain their existing failure behavior; this is not a whole-import
transaction guarantee. Pandoc is required for normalization as well as DOCX
conversion. Actual-export and rejection checks live in
`tests/build/test_entry_layout.py`; preflight-failure coverage lives in
`tests/ops/review/test_conversion.py`.

## Python Ownership

Under `cvworkbench.ops.review`, `packs.build_review_pack` owns bundles,
`importing.import_docx_review` owns import orchestration/draft writes,
`markdown` owns document conversion and shared comparison syntax, `targets`
resolves source runs, `patches` interprets edits, `record` owns provenance validation,
and `catalog` owns discovery and source health. `ReviewError` is the shared
operation error. The CLI adapts these operations; patch interpretation does
not depend on command parsing.

`targets.resolve_review_run` selects a retained run and review destination for
packaging. `targets.resolve_review_target` adds current source, variant, and
project-patch resolution for import. The latter reuses the run selector rather
than making bundle creation depend on mutable source inputs.
