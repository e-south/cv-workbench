# Operations rules

- Operations are side-effecting boundaries. Validate source, target, policy, and artifact contracts before the first write; fail closed on disagreement.
- Keep the publication boundary in `syncing.py` and `publish.py`. Build code produces artifacts and manifests; site repositories only receive the validated public PDF and sanitized provenance manifest.
- Local mode may write only the configured target. PR mode remains explicit and must verify a clean Git repository before branch, commit, push, or pull-request operations.
- Never read from or publish a guessed Source of Truth path. Use resolved configuration and surface missing inputs as errors.
- Add negative-path tests for malformed manifests, unsafe variants, invalid targets, and partial side effects.
