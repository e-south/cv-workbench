# Verify Contract

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
- `import-docx`: `patch.diff`, `notes.md`, and `imported.md` exist and resolve
  the same latest run id as `reviewpack`

## Failure contract

- Any preflight or artifact assertion failure sets `status: failed`
- The run stops at the first failing step
- The summary keeps completed-step evidence and records the explicit error
