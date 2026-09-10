---
id: reference-publication-contract
intent: Define authored publication provenance, freshness, and recorded review before site handoff.
audience: [operator, agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Authored Publication Lifecycle

The editable DOCX and its authoring-app PDF export are explicit inputs to
`prepare-public-pdf`. Generated resume builds do not update this source pair.
Publication commands default to `site.publish_variant` in `site-sync.yaml`,
independently of the default generated-document variant. Pass `--variant` to
select another declared publication explicitly; missing selection is surfaced
without guessing from build output.
The source correspondence check is a token-coverage check; it does not prove
that an export was made after every edit or has identical wording and order.

## Private preparation record

Preparation atomically writes `preparation.json` beside the prepared PDF and
manifest under the configured publish directory. This private record stores
the selected input paths and hashes, the publication policy, variant and person
hashes, the public PDF and manifest hashes, and the visual packet file hashes.
It is a snapshot of the inputs used for this preparation, not another editable
CV or a replacement for the authored source. It never crosses the site boundary.
Preparation and review records are written with owner-only permissions (`0600`).

`publication status` and the `context` publication section inspect current bytes.
They report unconfigured, untracked, missing, stale_source, stale_export,
stale_configuration, invalid, review_required, or reviewed. Reasons identify the
specific failed contract. Missing provenance is never inferred from filenames,
timestamps, the latest generated build, or the existence of a review directory.

## Review receipt

After inspecting the exact public PDF and page packet, the caller records review:

```bash
cvw publication review --pdf-sha256 <hash-shown-in-review-packet>
cvw publication status --json
```

The command checks current source, policy, artifact and packet integrity before
writing a private `review-receipt.json`. The receipt binds the caller's review
declaration to the PDF hash and preparation-record hash. It records a timestamp;
it is not proof that a human read the document. A changed preparation or damaged
packet requires review again. Repeating an identical preparation preserves a
still-current receipt.

The static packet identifies itself as review evidence, not live lifecycle
status. Its content stays fixed after review is recorded; `publication status`
owns the current freshness and review verdict.

## Handoff

Sync requires current inputs and a matching receipt in addition to the existing
disclosure, fidelity, manifest and destination checks. It fails before any site
write when preparation is stale, missing or unreviewed. A reviewed state means
the local artifact is eligible for the sync checks; it does not claim that the
site has already been updated. Only the PDF and sanitized site manifest cross
that boundary.

Older prepared artifacts without a preparation record must be prepared again
with explicit source paths, reviewed, and then synced. There is no inferred
migration or automatic approval. See [the authored CV guide](../howto/publish-site.md)
for the operator journey and [the site contract](site-contract.md) for writes.

## Code ownership

`ops/publication/` owns the lifecycle: `record.py` defines the private schemas,
`state.py` inspects freshness and records review, `pdf.py` performs sanitization,
`packet.py` renders review evidence, `policy.py` loads disclosure policy, and
`artifact.py` validates manifest eligibility. Python consumers use these modules;
the former flat `ops/public_pdf.py`, `ops/publish.py`, and
`ops/publication_review.py` paths have moved. CLI spellings for preparation and
sync remain unchanged. `cli/publication.py` owns their adapters plus the
`publication status` and `publication review` commands; `workspace/publication.py`
owns the workflow description. Site writes remain in `ops/syncing.py`.
