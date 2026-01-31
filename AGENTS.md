## Browser / preview policy

You are operating inside the cv-workbench repo.

Primary rule: prefer deterministic CLI artifacts (manifest.json, selection.json, resume.json, canonical.md) over browser inspection for correctness.

When you must visually verify output (HTML/PDF):
1) Start the preview server:
   - run: uv run cvw preview --sot-path ./sot.sample --variant base
2) Use Playwright MCP as the interactive controller:
   - open a new tab
   - navigate ONLY to the local preview origin (localhost/127.0.0.1)
   - you MAY click/type/drive the UI proactively to validate behavior
   - capture artifacts to: var/runs/preview/<run-id>/
     - browser_snapshot -> ui.snapshot.md
     - browser_take_screenshot (fullPage=true if supported) -> ui.png
     - browser_console_messages (level=warning) -> console.txt
   - close the tab
3) Never navigate to public internet.

If Playwright MCP is unavailable:
- do not attempt OS-level browser automation
- fall back to CLI-only verification and clearly report what cannot be visually confirmed.
