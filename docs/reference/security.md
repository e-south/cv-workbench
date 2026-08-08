---
id: reference-security
intent: Define private-data, publication, dependency, and automation security boundaries.
audience: [operator, agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Security

- Personal SoT data must live outside this repo.
- `local/sot/`, `var/dist/`, `var/runs/`, `var/drafts/`, `var/registry/`, `var/reviews/`, and `var/projects/` are ignored by git.
- Public variants must omit forbidden contact fields and sections in addition
  to excluding private tags. Tag filtering alone does not protect top-level
  contact fields.
- Authored CV preparation validates DOCX/PDF correspondence, rejects macros,
  removes prohibited contact and section content, strips hidden PDF payloads,
  rejects hidden or non-HTTPS links and non-text visual payloads that cannot be
  verified, anchors section removal to exact headings, and validates that every
  removed glyph falls inside a policy-derived region while every surviving
  glyph retains its visual geometry.
- Site sync reparses the PDF and validates current variant policy and artifact
  hash before writing. The site receives a sanitized provenance manifest, not
  source paths, authored-source hashes, or private SoT hashes.
- Pre-commit includes gitleaks to catch secrets before commit.
- `uv run cvw init` installs pre-commit hooks when a `.pre-commit-config.yaml`
  is present in the repo. Hook installation requires a writable `.git/hooks/`
  directory and a working `pre_commit` runtime from `uv sync --locked`.
- GitHub Actions use read-only repository permissions and immutable action
  commit pins. CodeQL analyzes Python and workflow code on pull requests,
  default-branch pushes, and a weekly schedule.
- Dependabot owns uv, pre-commit, and GitHub Actions update proposals. Review
  generated lockfile and action-pin changes through the same required checks as
  human-authored pull requests.
- CI installs the locked environment and runs `pip-audit`; known dependency
  vulnerabilities fail a dedicated check instead of relying on update cadence.
- Codex review guidance lives in scoped `AGENTS.md` files. Deterministic checks
  stay in CI; review rules focus on publication boundaries, artifact integrity,
  and unsafe side effects.
