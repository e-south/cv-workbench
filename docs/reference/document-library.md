---
id: reference-document-library
intent: Find private career documents and deliberately promote reviewed files to current.
audience: [operator, agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Document library

A document library owns durable personal files outside the tool checkout.
cv-workbench owns editing and rendering software. A site or an application
receives a separately selected artifact; neither owns the source record.

## Locations and identity

Use `current/` for deliberately promoted documents, `working/` for authoring and
review, `archive/` for predecessors, and `records/promotions/` for private receipts.
Existing `guidance/` and other records remain independent. Document filenames
and working-folder names need not match workbench variant identifiers.

An optional `documents.root` setting in `config/workbench.yaml` selects a library,
relative to that configuration file. An explicit `--root` selects it for a command.
No home-directory search, environment discovery, file-age ranking, or implicit
library creation occurs. A library does not require a native source or a project.

```yaml
documents:
  root: /path/to/private/career-documents
```

A document has an explicit ID, kind (CV, resume, letter, or another useful label),
edition, and audience (`application`, `private`, or `public`). A native variant is
a rendering recipe, not an approval state. A revision changes content; a promotion
makes reviewed files current. Publication and submission remain separate actions.

## Find and inspect

```sh
cvw documents list --root /path/to/private/career-documents --json
cvw documents list --config /path/to/private/config/workbench.yaml --json
cvw documents list --root /path/to/private/career-documents --path /path/to/private/career-documents/working/example --json
```

Default inspection is bounded to `current/` and `working/`. Explicit paths must
remain inside the chosen library. PDF, DOCX, DOC, ODT, RTF, Markdown, and text files
are visible without metadata. Hidden files, Word lock files, README/AGENTS routers,
and linked directories are not followed. With a configuration, source versions,
themes, configuration, and the workspace's generated `var/` store are excluded
from the default document view; configured native recipes are listed separately.

Promotion receipts provide optional document identity and editable-source routing.
An unchanged promoted artifact reports `current`; a changed artifact reports
`modified`. A deleted promoted artifact reports `missing` with its receipt and
editable-source route. A file without a receipt reports `unrecorded`, not rejected or approved.
Conflicting or malformed history appears as an issue and blocks promotion and GC.
The list command returns exit 2 when inspection has issues, and exit 1 for an
invalid request. `context` includes the configured library and a list command.

## Promote a reviewed set

Write an explicit JSON request beside the working files. Source paths resolve
relative to the request. Destination paths resolve relative to the library and
must stay below `current/`. File extensions must remain unchanged.

```json
{
  "schema_version": 1,
  "document": {
    "id": "general-cv",
    "kind": "cv",
    "edition": "general",
    "audience": "application"
  },
  "source": {"kind": "authored", "path": "edited-cv.docx"},
  "files": [
    {"source": "edited-cv.docx", "destination": "current/cv/application/cv.docx"},
    {"source": "exported-cv.pdf", "destination": "current/cv/application/cv.pdf"}
  ]
}
```

```sh
cvw documents promote --root /path/to/private/career-documents --request /path/to/private/promotion.json --json
cvw documents promote --root /path/to/private/career-documents --request /path/to/private/promotion.json --apply --reviewed-sha256 <inspected-plan-sha256> --json
```

The first command only plans. Inspect the source, destinations, current-file hashes,
and retired files before applying. The plan hash binds that exact request and
captured state; changed inputs require a new plan. This declaration records review
by the caller. It does not infer review from a build, timestamp, or filename.

Authored files stay authored: local promotion copies exact bytes and does not
convert DOCX to YAML or assert that a manually exported PDF matches its DOCX.
Review that correspondence before promotion. Native requests instead use:

```json
{"kind":"native","config":"config/workbench.yaml","path":"source-versions/versions/revision","variant":"base","run":"var/runs/explicit-run-id"}
```

The native source must be explicit. Configuration, variant, source/snippet hashes,
and selected run outputs must match. This reuses the same native-input attestation
as publication. Run files remain immutable; edit the source or a native review copy,
then build a new run. See [content review](review-contract.md) for supported imports.

A public document must use a publication source:

```json
{"kind":"publication","config":"config/workbench.yaml","variant":"public-cv"}
```

It accepts only the exact prepared PDF, after the existing disclosure, freshness,
and exact-PDF review gates pass. An application or private source cannot be
relabeled public. See [publication](publication-contract.md). Local promotion does
not sync a site, create a PR, send an application, or grant external access.
See the [site contract](site-contract.md) for configuration selection and handoff.

## Preservation, conflicts, and recovery

Each successful promotion writes a receipt beneath
`records/promotions/<document-id>/<plan-sha256>.json`. Receipts contain private paths
and hashes and form an explicit predecessor chain. Current selection follows that
chain, never filesystem modification time. Do not publish these receipts.

Replaced and retired files are copied beneath
`archive/promotions/<document-id>/<plan-sha256>/`, preserving their relative current
paths. The request's files are the complete next set: removed/renamed outputs are
shown as retired in the plan and archived before their old paths are removed.
Native source runs referenced anywhere in the promotion history are retained by
[run cleanup](artifact-retention.md), even when source content subsequently changes.

Unrecorded existing destinations and destinations owned by another document are
rejected. Choose an unused destination or explicitly archive an unrecorded file
before replanning. Modified promoted files also block replacement by default.
To reconcile intentional manual edits, preserve them in the working source and
set `replace_modified_current: true` in a new request. Review its new plan; the
changed current bytes are archived before replacement. A build alone never
updates `current/`.

Cooperating promotions use a nonblocking library lock. A busy library reports an
error; it does not silently queue another write. Inputs are recaptured before
commit, and destination bytes are checked before and after staging. File changes,
archives, and the receipt use the shared recoverable replacement operation.
Injected failures and cancellation restore prior files; incomplete rollback
reports the retained recovery paths. This is not a distributed transaction with
editors, cloud sync clients, or another computer, nor a guarantee against power loss. Avoid
simultaneous editing while applying; inspect any reported recovery paths before retrying.

## Ownership and checks

- `workspace/documents.py`: bounded, read-only inventory and context routing.
- `ops/documents/records.py`: request/receipt schemas and chain interpretation.
- `ops/documents/sources.py`: authored/native/publication evidence adapters.
- `ops/documents/promotion.py`: plan, conflict checks, archival, and commit.
- `ops/documents/retention.py`: exact source-run references for cleanup.
- `inputs/native_run.py`: shared native build attestation.
- `cli/commands/library.py`: command parsing and local presentation.

No document contents or environment values belong in inventory, promotion plans,
receipts, or public package fixtures. Local command output does contain the
explicitly selected private paths and identities; keep that output private.

```sh
uv run pytest tests/ops/test_document_promotion.py tests/ops/test_document_retention.py tests/ops/test_document_privacy.py tests/workspace/test_documents.py tests/cli/test_documents.py
```
