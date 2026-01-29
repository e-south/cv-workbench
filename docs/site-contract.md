# Site Contract

Default sync expects an Astro site repo with:

- `src/content/cv/cv.md`
- `public/cv/<configured>.pdf`
- `src/content/page-cv/cv.md` (frontmatter references the PDF)

The sync command defaults to local updates. PR sync is opt-in.

`config/site-sync.yaml` must declare a `publish_variant` that is the only
variant eligible for sync.

`config/publish.yaml` further restricts which variants can be synced to public
targets.

`repo_path` in the site sync config is resolved relative to the config file
location.
