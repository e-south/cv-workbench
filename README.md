# cv-workbench

[![CI](https://github.com/e-south/cv-workbench/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/e-south/cv-workbench/actions/workflows/ci.yml?query=branch%3Amain)

A deterministic CV/resume workbench. This repository is the public engine;
private CV content lives in a separate Source of Truth (SoT) directory outside
git.

Use [docs/readme.md](docs/readme.md) as the canonical docs router. The root
README stays intentionally light; `docs/readme.md` routes the full workflow and
contract surface.

> [!NOTE]
> Preview/browser hardening update (March 11, 2026)
>
> - Session ownership is explicit in the preview contract: `session.json` and `/api/state` carry a `session_id`, preview startup rejects an already-live session instead of silently overwriting it, stale session files are cleared, and `dev stop --force` no longer reports success if the preview port is still busy. See [src/cvworkbench/cli/app.py](src/cvworkbench/cli/app.py), [src/cvworkbench/dev/preview.py](src/cvworkbench/dev/preview.py), and [docs/reference/preview-contract.md](docs/reference/preview-contract.md).
> - The preview page enforces a single active controller tab per session. A newer tab claims the session, older tabs become passive, disable controls, and stop polling instead of remaining competing live controllers, and a released/stopped session does not silently wake every remaining tab back up. See [src/cvworkbench/dev/preview.py](src/cvworkbench/dev/preview.py).
> - Button responsiveness is materially better because format switches reuse already-built outputs locally, non-force control changes are debounced/coalesced before rebuild, steady-state summary DOM updates are suppressed, and redundant render requests are collapsed instead of stacking up. See [src/cvworkbench/dev/preview.py](src/cvworkbench/dev/preview.py) and [docs/reference/preview-contract.md](docs/reference/preview-contract.md).
>
> Verification:
>
> - Baseline before the first hardening pass: `build_once(html+pdf)` averaged `2.19s`; a rebuild after initial build averaged `4.41s`; switching `html -> pdf` also averaged `4.41s`.
> - Tests passed: `uv run pytest -q tests/cli/test_preview.py tests/cli/test_dev_stop.py tests/cli/test_dev_serve.py tests/dev/test_preview_session.py tests/dev/test_preview_contract.py tests/ux/test_preview.py`
> - Local Chrome DevTools smoke check validated local format switching with no redundant `POST /api/render`, passive-tab takeover, and artifacts under `var/runs/preview/hardening-20260311/`.
>
> This hardening is ownership-first: one live preview session, one active controller tab, no silent stale-session reuse, and fewer unnecessary rebuilds during fast operator interaction.

## Start Here

- Python 3.12
- uv
- Pandoc (for rendering)
- LaTeX engine (xelatex) for PDF output

```bash
uv sync --locked
uv run cvw init --sample-default
uv run cvw doctor
uv run cvw quickstart
```

Common entry points:
- [First successful local build](docs/howto/quickstart.md)
- [Agent/bootstrap contract](docs/reference/context-contract.md)
- [Build and preview contract](docs/reference/preview-contract.md)
- [Job tailoring and project workflows](docs/howto/ingestion.md)
- [Review/import and guarded patching](docs/reference/project-contract.md)

Deterministic bootstrap commands:

```bash
uv run cvw context --json --compact
uv run cvw workflow --id automation.verify
uv run cvw workflow --id automation.verify --json --compact
uv run python scripts/verify_repo.py
```

## Core Workflows

- deterministic `build`, `render`, and `preview` flows
- project-scoped job tailoring with proposal variants and `project-ops` patches
- immutable run artifacts, review packs, and DOCX import drafts
- variant lifecycle, SoT versioning, and local site sync support

## Documentation Map

- [docs/readme.md](docs/readme.md): task-first docs index
- [docs/concepts/overview.md](docs/concepts/overview.md): CLI surface and feature lanes
- [docs/concepts/architecture.md](docs/concepts/architecture.md): repo boundaries and design constraints
- [docs/howto/](docs/howto/): operator guides
- [docs/reference/](docs/reference/): command contracts and invariants
- [docs/reference/verify-contract.md](docs/reference/verify-contract.md): repo-local verify harness contract

## License

MIT
