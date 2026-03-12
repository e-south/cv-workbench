# Quickstart

This guide walks through the fastest local path to a generated CV using the
sample SoT data. It is safe to run in this public repo.

After the initial setup, choose one lane:
- `quickstart` for the fastest sample build.
- `context --json --compact` plus `workflow --id ... --json --compact` for deterministic agent bootstrap.
- `build` plus `preview` when you want explicit control over formats and preview state.

## Requirements

- Python 3.12
- uv (https://docs.astral.sh/uv/)
- Pandoc (for rendering)
- LaTeX engine (xelatex) for PDF output

macOS (Homebrew):
```bash
brew install pandoc mactex-no-gui
eval "$(/usr/libexec/path_helper)"
```

## 1) Install dependencies

```bash
uv sync --locked
```

## 2) Initialize the workspace

```bash
uv run cvw init --sample-default
```

`uv run cvw init` installs pre-commit hooks when a `.pre-commit-config.yaml`
is present in the repo. If hook installation fails, `init` prints
`pre_commit_hooks: error` plus a detail line with the underlying reason.

Use `--sample-default` in this public repo when you want the configured default
SoT to be `./sot.sample`. Omit the flag when you want the scaffold to copy the
sample data into `./local/sot` for later replacement with private data.

## 3) Confirm the runtime toolchain

```bash
uv run cvw doctor
```

Optional agent bootstrap snapshot:

```bash
uv run cvw context --json --compact
uv run cvw workflow --id automation.verify
uv run cvw workflow --id automation.verify --json --compact
```

`context --json --compact` keeps the bootstrap payload small and includes
`recommended_workflows` with exact `command` and `json_command` follow-up
commands. Treat the emitted strings as authoritative; when you run from outside
the repo root they may include `uv run --project <repo> cvw ...`.
If the configured SoT is missing or invalid, those recommendations switch to
the explicit repair/bootstrap workflows instead of suggesting build commands.

Optional workspace status snapshot:

```bash
uv run cvw status
```

## 4) Fastest sample build

```bash
uv run cvw quickstart
```

This runs validation + build for the `base` variant and prints the output
locations. The default outputs are written to:

`uv run cvw quickstart` also creates the default scaffold (config, variants, and
templates) if they are missing.

If you skip step 2 and still want the workspace config to point at `./sot.sample`,
run `uv run cvw quickstart --sample-default`.

- `var/dist/base/cv.md`
- `var/dist/base/cv.pdf`
- `var/dist/base/cv.docx`
- `var/dist/base/manifest.json`
- `var/runs/<timestamp>/canonical.md`
- `var/runs/<timestamp>/resume.json`
- `var/runs/<timestamp>/selection.json`

You can run these commands from any subdirectory inside the repo. When a
workspace already exists, `init` and `quickstart` walk up to the nearest
`config/workbench.yaml` and resolve outputs relative to that configuration.

## 5) Agent/bootstrap lane

```bash
uv run cvw context --json --compact
uv run cvw workflow --id automation.verify --json --compact
```

Use the `workflow` command when you want one narrow recipe instead of the full
workspace snapshot.

## 6) Follow-up: build explicitly (recommended for automation)

```bash
uv run cvw build --sot-path ./sot.sample --variant base --format md,pdf
```

Use `--plain` for script-friendly text output or `--json` for machine-readable
payloads:

```bash
uv run cvw build --plain --sot-path ./sot.sample --variant base --format md
uv run cvw build --json --sot-path ./sot.sample --variant base --format md
```

## 7) Follow-up: sync to your site (local-first)

```bash
uv run cvw sync --variant base --site /path/to/astro-site
```

`uv run cvw sync` defaults to local mode. PR sync is opt-in via `--mode pr`.

## 8) Follow-up: preview styling quickly

```bash
uv run cvw theme list
uv run cvw theme info editorial
uv run cvw preview --sot-path ./sot.sample --variant base --style-preset modern
uv run cvw preview --sot-path ./sot.sample --variant base --style-preset compact
uv run cvw preview --sot-path ./sot.sample --variant base --theme signal --style-preset compact
```

`uv run cvw preview` starts a live preview server and auto-rebuilds when you edit SoT
files, theme templates, or style presets. The command prints a local preview URL;
use Chrome DevTools MCP to open and interact with the preview UI (sidebar
controls and shortcuts). The sidebar controls (or shortcuts) let you cycle
themes, presets, variants, and formats:

- `t`: cycle theme
- `p`: cycle style preset
- `v`: cycle variant
- `f`: cycle format (HTML/PDF/MD/ATS)
- `r`: rebuild with current settings
- `x`: stop the preview server

Closing the browser tab leaves the preview server running only until its idle
timeout expires. By default the server auto-stops after 30 seconds without
browser activity. Use the Stop button (or `x`) in the control bar, or run:

```bash
uv run cvw dev stop
```

To disable the idle timeout:

```bash
CVW_DEV_IDLE_TIMEOUT_SECONDS=0 uv run cvw preview --sot-path ./sot.sample --variant base
```

To change the local loopback host or port:

```bash
CVW_DEV_HOST=127.0.0.1 CVW_DEV_PORT=8877 uv run cvw preview --sot-path ./sot.sample --variant base
```

To see a styling change, edit the preset CSS and let the watcher rebuild:

```bash
$EDITOR build/themes/default/styles/html/compact.css
```

If you want the PDF to reflect the same preset:

```bash
uv run cvw build --sot-path ./sot.sample --variant base --format pdf --style-preset compact
```

## 9) Follow-up: save variants intentionally

`uv run cvw tailor` writes draft variants to `var/drafts/` and registers them as
ephemeral. Promote only the ones you want to keep:

```bash
uv run cvw variant keep --path ./var/drafts/<name>/variant.yaml --id <variant-id>
```

Project proposals use project selectors instead of raw proposal paths:

```bash
uv run cvw variant keep --project <project-id> --id <variant-id>
```

If a copied project proposal still carries a colliding id such as `base`,
`project show` and `variant inbox` will suggest a safe proposal id to keep.

To discard or clean up drafts:

```bash
uv run cvw variant discard --path ./var/drafts/<name>/variant.yaml --yes
uv run cvw variant discard --project <project-id> --yes
uv run cvw variant gc --yes
```

List pending drafts with:

```bash
uv run cvw variant inbox
```

List configured variants and lifecycle inbox together with:

```bash
uv run cvw variant list
```

The retention window is controlled by `variant_lifecycle.ttl_days` in
`config/workbench.yaml`.

## 10) Follow-up: start a project (job tailoring)

Guided path (recommended):

```bash
uv run cvw project guide --job-url "https://example.com/job"
uv run cvw project show <project-id>
uv run cvw preview --project <project-id>
uv run cvw build --project <project-id> --format md,pdf,docx
uv run cvw project show <project-id>
```

After the review-ready build completes, `project show` prints the pinned
`reviewpack --project <project-id> --run projects/<project-id>/<run-id>`
command for the latest immutable project run.

Before exporting review artifacts, compare the project run against an explicit
baseline run so you can see the scoped content delta:

```bash
uv run cvw build --variant base --format md,pdf,docx
uv run cvw build --project <project-id> --format md,pdf,docx
uv run cvw diff --artifact canonical --run-a <base-run-id-or-path> --run-b projects/<project-id>/<run-id>
uv run cvw diff --artifact resume --run-a <base-run-id-or-path> --run-b projects/<project-id>/<run-id> --format json
```

Use the explicit run ids printed by `build` or `project show`; `diff` is most
useful when you choose the exact baseline you want to compare rather than
assuming "latest" means the right thing.

Direct project creation when you already know the base variant:

```bash
uv run cvw project new --job-url "https://example.com/job" --variant base
uv run cvw project show <project-id>
uv run cvw preview --project <project-id>
```

To package a specific project build deterministically, use the run path emitted by
`build --project` or the pinned `project show` output:

```bash
uv run cvw build --project <project-id> --format md,pdf,docx
uv run cvw reviewpack --run projects/<project-id>/<run-id>
uv run cvw import-docx --from ./var/reviews/projects/<project-id>/cv.docx --project <project-id> --run projects/<project-id>/<run-id>
```

If you need to refresh an existing review pack for the same run, rerun
`reviewpack` explicitly with `--force`:

```bash
uv run cvw reviewpack --run projects/<project-id>/<run-id> --force
```

If you re-run either command for the same job, provide a unique `--slug` to
avoid colliding with an existing project directory.

Projects keep job context, signals, and proposal drafts without mutating SoT.

When you need a project-local content edit, use the guarded project patch
authoring command:

```bash
uv run cvw project patch replace-experience-bullet <project-id> \
  --role-id <role-id> \
  --bullet-id <bullet-id> \
  --new-text "Replacement text"

uv run cvw project patch replace-project-summary <project-id> \
  --project-id <project-id> \
  --new-text "Replacement text"
```

This appends a `project-ops` entry to `var/projects/<project-id>/proposals/patch.yaml`.
If you omit `--old-text`, the command snapshots the current SoT source text for
that bullet or project summary. `preview --project`, `build --project`, and
`project apply` all reuse the same compare-and-set contract.

When reviewed DOCX edits stay on supported resume surfaces, `import-docx` now
writes `var/drafts/import-*/patch.yaml` using the same `project-ops` schema.
Formatting-only normalized imports report `apply_status: ready_no_changes`.
Unsupported edits still fall back to `patch.diff` plus `apply_status:
review_diff_only`.

## 11) Follow-up: clean generated artifacts

```bash
uv run cvw clean runs --yes
uv run cvw clean dist --yes
uv run cvw clean drafts --yes
uv run cvw clean reviews --yes
uv run cvw clean registry --yes
uv run cvw clean projects --yes
```

To prune old runs without wiping everything, keep the most recent runs per
variant:

```bash
uv run cvw runs gc --keep-latest 2
uv run cvw runs gc --keep-latest 2 --yes
```

Clean commands default to a dry run unless `--yes` is provided.
