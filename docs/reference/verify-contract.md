---
id: reference-verify-contract
intent: Define the repository tracer-bullet verification contract.
audience: [agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Verify Contract

## Default test discovery

`uv run pytest` must collect every test-bearing file under `tests/`, including
the `tests/build/` domain. `pyproject.toml` explicitly defines recursion
exclusions; package directories must not inherit pytest's generic `build`
exclusion. A repository-contract regression compares an AST inventory of
test-bearing files with actual default pytest collection and lists omissions.

After changing test layout or runner configuration, check:

```bash
uv run pytest tests/test_repository_contracts.py -k discovery
uv run pytest
```

`scripts/verify_repo.py` is the repo-local tracer-bullet harness for the
package's canonical local journeys. It runs in an isolated temp workspace,
targets `./sot.sample`, and fails fast when the toolchain or artifact contract
drifts.

## Entry point

```bash
uv run python scripts/verify_repo.py
uv run python scripts/verify_repo.py --json
```

The harness always writes a machine-readable summary to:

```text
<workspace>/verify-summary.json
```

The workspace path is printed in the terminal output and included in the JSON
summary.

## Preconditions

- `uv`, `pandoc`, and the configured PDF engine are on `PATH`
- repo root contains `pyproject.toml`, `config/variants/*.yaml`, `build/themes/`
- `sot.sample/` validates successfully
- isolated artifact directories are writable before any CLI step runs

There is no fallback to `local/sot`, browser automation, or the checked-out
`var/` tree. Preflight failures stop the run immediately.

## Canonical journeys

The harness runs these commands in order against the isolated workspace config:

1. `cvw doctor`
2. `cvw context --json`
3. `cvw build --sot-path <repo>/sot.sample --variant base --format md,pdf,docx`
4. `cvw preview --once --sot-path <repo>/sot.sample --variant base`
5. `cvw project guide --job-file <workspace>/fixtures/job.txt --sot-path <repo>/sot.sample`
6. `cvw reviewpack --variant base`
7. `cvw import-docx --from <workspace>/var/reviews/base/cv.docx --variant base`

## Required evidence

The summary plus per-step raw stdout/stderr are stored under:

```text
<workspace>/evidence/
```

Required artifact assertions:

- `doctor`: both `pandoc` and the configured PDF engine report `ok`
- `context`: `sot.status == "ready"` and recipe order starts with
  `baseline.build_preview`, `automation.verify`, `review.import`,
  `project.guide`
- `build`: `cv.md`, `cv.pdf`, `cv.docx`, both manifests, `canonical.md`, and
  `resume.json` exist under the isolated workspace
- `preview --once`: `cv.html` exists, the returned `preview_file` resolves to
  that local HTML path, and no preview session file is written
- `project guide`: `project.yaml`, `proposals/variant.yaml`, and
  `proposals/patch.yaml` exist
- `reviewpack`: `cv.docx`, `cv.pdf`, and `review.md` exist and resolve the same
  run id created by `build`
- `import-docx`: `patch.diff` or `patch.yaml`, `draft.json`, `notes.md`, and
  `imported.md` exist and resolve the same latest run id as `reviewpack`

## Failure contract

- Any preflight or artifact assertion failure sets `status: failed`
- The run stops at the first failing step
- The summary keeps completed-step evidence and records the explicit error

## Installed distribution

```bash
uv run pytest tests/distribution/test_installed_wheel.py
```

This test builds and installs a wheel into a new virtual environment, executes
its installed entry point in an empty workspace, and asserts that both code and
resource paths come from that installation. It reuses runtime dependencies from
the locked test environment without processing its editable `.pth` files or
adding the source checkout to the child interpreter's import path. Dependency
resolution is separately exercised by `uv sync --locked` in CI.

The journey checks init, doctor, context, Markdown/PDF/DOCX resume and
cover-letter exports, and one-shot HTML preview. It also checks neutral
publication defaults, installed-runtime command suggestions, and preservation
of workspace configuration and theme edits after reinitialization. Each command
writes stdout/stderr beneath the pytest temporary directory's `evidence/`.
The test runs as part of the ordinary CI pytest suite; it requires the same
Pandoc and LaTeX toolchain as the checkout journey. Set `UV_OFFLINE=1` to verify
with cached build tooling and no package downloads.
