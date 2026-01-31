## Browser / preview policy

You are operating inside the cv-workbench repo.

Primary rule: prefer deterministic CLI artifacts (manifest.json, selection.json, resume.json, canonical.md) over browser inspection for correctness.

When you must visually verify output (HTML/PDF):
1) Start the preview server with OS auto-open disabled:
   - run: CVW_SKIP_OPEN=1 uv run cvw preview --sot-path ./sot.sample --variant base
2) Use Playwright MCP in read-only mode:
   - open a new tab
   - navigate ONLY to the local preview origin (localhost/127.0.0.1)
   - capture:
     - browser_snapshot saved to runs/preview/<run-id>/ui.snapshot.md
     - browser_take_screenshot saved to runs/preview/<run-id>/ui.png (fullPage=true if supported)
     - browser_console_messages saved to runs/preview/<run-id>/console.txt (level=warning)
   - close the tab
3) Never navigate to public internet. Do not click/type/fill unless I explicitly ask.

If Playwright MCP is unavailable:
- do not attempt OS-level browser automation
- fall back to CLI-only verification and clearly report what cannot be visually confirmed.

