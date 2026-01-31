# Journal

## 2026-01-31
- Preview server now serves files from the current controller state so variant switches do not 404.
- Removed legacy preview viewer/open-mode flags and reject legacy preview env vars.
- Added Playwright preview control selectors and a contract test for stable UI hooks.
- Updated docs to reflect Playwright-first preview and local/var layout paths.
- Completed Playwright-first preview refactor and repo layout consolidation (local/ + var/).
- Init now creates var/dist, var/runs, var/drafts, and var/reviews so clean is idempotent.
- Quickstart output now points to `cvw preview` instead of `cvw dev serve`.
- Preview watcher now includes variants and themes roots to detect new assets.
- Preview session parsing now fails fast on missing fields.
- Added variant lifecycle registry with keep/discard/gc/inbox flows.
- Tailor and project creation now register ephemeral variants for cleanup.
- Init scaffolding now creates `var/variants` alongside other var targets.
- Preview UI now surfaces disconnected-state errors and marks the active format button for automation.
- Sync fails fast if the site repo path is missing or not a directory.
- Added `cvw preview --once` for one-shot preview builds without starting the server.
- Added `cvw status` to summarize SoT, variants, runs, projects, and reviews.
- Added `cvw variant list` and `cvw project guide` for variant and project discovery.
- Reviewpack now requires a valid run manifest; import-docx can resolve the latest run by variant.
- Signals keyword extraction now filters common stop words for clearer job guidance.
- Added `cvw runs gc` to prune older runs while keeping recent ones per variant.
- Added `cvw context` as a bootstrap command with recipes for common workflows.
