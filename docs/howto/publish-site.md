---
id: howto-publish-site
intent: Prepare and publish a faithful authored CV without exposing private contact or reference data.
audience: [operator, agent]
status: active
navigation:
  parent: ../readme.md
---

# Publish The Authored CV

Use this lane when the public artifact must retain the layout of an editable
Word CV. It is distinct from the generated resume lane: the DOCX remains the
editable presentation authority, while structured SoT continues to power
selection and tailored variants.

## Inputs

Keep both inputs outside git:

- the canonical editable `.docx`;
- a PDF exported from that DOCX with the authoring application.

The preparation command verifies token-frequency coverage from DOCX to PDF and
from PDF to DOCX, removes fields and sections prohibited by
`config/publish.yaml`, strips hidden or embedded payloads, rejects hidden or
non-HTTPS links, and validates the result before replacing
`var/publish/<variant>/cv.pdf`. The manifest records content hashes and the
transformation without publishing local paths.

## Prepare

```bash
uv run cvw prepare-public-pdf \
  --authored-source /private/path/to/cv.docx \
  --source-pdf /private/path/to/exported-cv.pdf \
  --plain
```

Review `var/publish/base/cv.pdf` visually. Then sync only the validated PDF and
sanitized manifest:

```bash
uv run cvw sync --mode local --plain
```

## Failure Policy

Preparation and sync fail closed when the source pair is unrelated, the PDF is
invalid or encrypted, embedded files are present, a forbidden phone or section
survives, an unauthorized email or hidden link appears, provenance or policy
metadata disagrees, a destination escapes the configured site repository, or
any removed character falls outside an exact policy-derived redaction region,
or any surviving character changes its page, order, origin, bounding box, font,
size, style flags, or color. Section removal starts at the exact heading line,
not an earlier prose mention. Do not replace this lane with a Markdown-to-PDF
rebuild when layout fidelity is the requirement.

Continue with [the site contract](../reference/site-contract.md) for ownership
and write-boundary details, then [security](../reference/security.md) for the
public disclosure policy.
