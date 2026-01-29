# Site Contract

Default sync expects an Astro site repo with:

- `src/content/cv/cv.md`
- `public/cv/<configured>.pdf`
- `src/content/page-cv/cv.md` (frontmatter references the PDF)

The sync command supports PR-based updates by default.

`config/site-sync.yaml` must declare a `publish_variant` that is the only
variant eligible for sync.

`repo_path` in the site sync config is resolved relative to the config file
location.
