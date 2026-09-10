# Operations rules

- Operations are side-effecting boundaries. Validate source, target, policy, and artifact contracts before the first write; fail closed on disagreement.
- Keep the publication boundary in `syncing.py` and `publication/`: site writes belong to the former, authored preparation/policy to the latter. Read the publication directory's scoped `AGENTS.md` when changing that lifecycle. Build code produces artifacts and manifests; site repositories only receive the validated public PDF and sanitized provenance manifest.
- Local mode may write only the configured target. PR mode remains explicit and must verify a clean Git repository before branch, commit, push, or pull-request operations.
- Never read from or publish a guessed Source of Truth path. Use resolved configuration and surface missing inputs as errors.
- `patches.py` owns captured unified-diff execution in temporary workspaces and
  recoverable source writes. Route draft/project application through it; keep
  eligibility and stable-target interpretation in their domain owners. Read
  `docs/reference/patch-application.md` before changing this mutation boundary.
- Read `projects/AGENTS.md` when changing project lifecycle, guidance, manifests, or guarded edits; it routes to the public operation contract and internal owners.
- Add negative-path tests for malformed manifests, unsafe variants, invalid targets, and partial side effects.
