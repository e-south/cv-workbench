# Security

- Personal SoT data must live outside this repo.
- `local/sot/`, `var/dist/`, `var/runs/`, `var/drafts/`, `var/registry/`, `var/reviews/`, and `var/projects/` are ignored by git.
- Pre-commit includes gitleaks to catch secrets before commit.
- `uv run cvw init` installs pre-commit hooks when a `.pre-commit-config.yaml`
  is present in the repo. Hook installation requires a writable `.git/hooks/`
  directory and a working `pre_commit` runtime from `uv sync --locked`.
