---
id: reference-site-contract
intent: Define the fail-closed boundary for publishing a CV artifact to a site.
audience: [operator, agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Site Contract

Default sync expects a site repository with:

- `public/cv/<configured>.pdf`
- a configured sanitized publication-manifest destination
- `src/content/page-cv/cv.md` (frontmatter references the PDF)

The site owns presentation only. It must not copy canonical CV Markdown or
re-render a second HTML CV. The workbench owns selection, authored-artifact
preparation, disclosure policy, and artifact provenance.

For the public base CV, `cvw prepare-public-pdf` accepts the canonical editable
DOCX and a faithful PDF export. It checks that they correspond, applies semantic
redactions, strips hidden payloads, and emits the only PDF eligible for sync.
See [Publish The Authored CV](../howto/publish-site.md).

Preparation commits the public PDF, provenance manifest, and local visual
review packet as one recoverable update. The packet is indexed by the sanitized
PDF hash under `var/reviews/publication`; it never crosses the site boundary.
Sync applies the PDF, page frontmatter, and sanitized site
manifest through the same staged replacement primitive while preserving each
existing destination mode.

Publish-eligible artifacts live under `var/publish/<variant>`, separate from
ordinary generated outputs under `var/dist`. Sync never falls back to `dist`,
so a resume build or test cannot replace the reviewed authored artifact.

Before its first write, sync verifies:

- the selected source/export pair and publication inputs still match their
  private preparation record, and the current PDF has a matching review receipt;
- the source is a parseable, unencrypted PDF without embedded files;
- the manifest identifies an authored PDF publication produced by semantic
  redaction and names the selected variant and PDF;
- the PDF SHA-256 matches the build manifest;
- manifest selection fields match the current variant;
- all required exclusion tags are present; and
- forbidden contact fields and sections are absent; and
- no third-party email or hidden/unsafe link survives the public allowlist.

Both CLI and Python API sync require a publication policy. When the API omits
an explicit policy path, it resolves `publish.yaml` beside the workbench config;
a missing file fails before any site write. Sync also recomputes the actual PDF
rectangle fingerprint, rather than relying on its declaration in the manifest.

Sync copies only the PDF, updates its configured page-frontmatter path, and
writes a sanitized manifest containing the public path, artifact hash, variant,
and disclosure policy. Source paths, SoT hashes, and private content never cross
the site boundary.

Sync captures PDF bytes once for manifest identity and disclosure validation.
The current review receipt must identify that same captured PDF hash; a review
for another publication generation stops sync. The immutable copy plan carries
those validated bytes through destination comparison and atomic replacement.
It never reopens the PDF source to perform the copy. Replacing the source after
planning therefore cannot substitute unreviewed bytes or make the destination
disagree with the sanitized manifest hash. This binds artifact content for the
operation; it does not lock source files or configuration against other writers.

All changed outputs are staged before replacement. If any replacement fails,
sync restores every previously replaced artifact before returning an error, so
the PDF, frontmatter, and manifest cannot remain at mixed generations.

If filesystem errors prevent rollback itself, the command reports an incomplete
rollback and retains the affected backup files at the paths in the error. Stop
syncing and recover those originals before retrying. Staging failures clean up
temporary files without touching the prior artifacts.

The sync command defaults to local updates. PR sync is opt-in and additionally
requires a clean Git target before it creates a branch.

`config/site-sync.yaml` must declare a `publish_variant` that is the only
variant eligible for sync.

`config/publish.yaml` is the public disclosure policy. It restricts eligible
variants, required exclusion tags, forbidden contact fields, and forbidden
sections.

`repo_path` in the site sync config is resolved relative to the config file
location. Every configured destination must remain beneath that resolved
repository; absolute and parent-traversal destinations are rejected before the
first write.

Sync fails fast if the repo, page, manifest, artifact, or policy contract is
missing or inconsistent. It does not fall back to Markdown, an older PDF, or a
different variant.
