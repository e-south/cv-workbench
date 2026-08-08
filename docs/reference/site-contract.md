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

Publish-eligible artifacts live under `var/publish/<variant>`, separate from
ordinary generated outputs under `var/dist`. Sync never falls back to `dist`,
so a resume build or test cannot replace the reviewed authored artifact.

Before its first write, sync verifies:

- the source is a parseable, unencrypted PDF without embedded files;
- the manifest identifies an authored PDF publication produced by semantic
  redaction and names the selected variant and PDF;
- the PDF SHA-256 matches the build manifest;
- manifest selection fields match the current variant;
- all required exclusion tags are present; and
- forbidden contact fields and sections are absent; and
- no third-party email or hidden/unsafe link survives the public allowlist.

Sync copies only the PDF, updates its configured page-frontmatter path, and
writes a sanitized manifest containing the public path, artifact hash, variant,
and disclosure policy. Source paths, SoT hashes, and private content never cross
the site boundary.

All changed outputs are staged before replacement. If any replacement fails,
sync restores every previously replaced artifact before returning an error, so
the PDF, frontmatter, and manifest cannot remain at mixed generations.

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
