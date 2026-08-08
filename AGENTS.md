## Browser / preview policy

You are operating inside the cv-workbench repo.

Primary rule: prefer deterministic CLI artifacts (manifest.json, selection.json, resume.json, canonical.md) over browser inspection for correctness.

## Agent startup context

On session start, run:
- `uv run cvw context --json`

Use the `recipes` block in the context payload to choose commands for any
user intent. Do not guess paths or commands before reading context. If context
reports missing or invalid SoT, ask for the correct SoT path or config updates
before proceeding.

Strict policy:
- Local preview only (localhost/127.0.0.1).
- No public internet access.
- Minimal tools by default; use Chrome DevTools MCP only when visual verification is required.

When you must visually verify output (HTML/PDF):
1) Start the preview server:
   - run: uv run cvw preview --sot-path ./sot.sample --variant base
2) Use Chrome DevTools MCP as the interactive controller:
   - open a new tab
   - navigate ONLY to the local preview origin (localhost/127.0.0.1)
   - you MAY click/type/drive the UI proactively to validate behavior
   - capture artifacts to: var/runs/preview/<run-id>/
     - `take_snapshot` -> ui.snapshot.md
     - `take_screenshot` (fullPage=true when useful) -> ui.png
     - `list_console_messages` (warnings) -> console.txt
   - close the tab
3) Never navigate to public internet.

If Chrome DevTools MCP is unavailable:
- do not attempt OS-level browser automation
- fall back to CLI-only verification and clearly report what cannot be visually confirmed.

## Code Review Rules

### Publication boundary

- Treat `local/` and `var/` as private. Flag any change that commits their data or publishes phone numbers, references, third-party contacts, or source manifests. The safe path is a configured public variant followed by the publish-policy and artifact-hash gates.

### Artifact integrity

- A `.pdf` publication must begin with the PDF signature and match its deterministic manifest hash. Preserve the target extension during atomic rendering, and fail closed when the manifest, variant policy, or artifact disagree.

### Side effects

- Keep local sync as the default and PR creation explicitly opt-in. Commands that write another repository must validate the target and publication policy before writing; do not add silent fallbacks.
