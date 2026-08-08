## Purpose

<!-- Explain the user-facing or maintainer-facing outcome. -->

## Verification

- [ ] `uv run pre-commit run --all-files`
- [ ] `uv run pytest`
- [ ] Public artifact changes were built and inspected from the intended variant.

## Data and publication boundary

- [ ] No private Source of Truth data, local artifacts, credentials, or third-party contact details were committed.
- [ ] Changes to the publication boundary preserve the required exclusions and fail closed on invalid artifacts.

## Review

After deterministic checks pass, request a focused Codex review in a PR comment with `@codex review`. For publication or privacy-sensitive changes, also request the repository's configured security review where available.
