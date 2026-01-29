# Site Contract

Default sync expects an Astro site repo with:

- `src/content/cv/cv.md`
- `public/cv/<configured>.pdf`
- `src/content/page-cv/cv.md` (frontmatter references the PDF)

The sync command supports PR-based updates by default.
