# cv-workbench

A lean, decoupled CV/Resume workbench. This repo is the public engine; real CV
content lives in a private Source of Truth (SoT) directory outside this repo.

Key goals:
- Deterministic builds from structured SoT
- Variant generation via data + filters
- Auditable outputs (local run manifests)
- MCP-ready CLI surface (`validate`, `build`, `render`, `tailor`, `diff`, `sync`)

## Quickstart (local)

Requirements:
- Python 3.12
- uv (https://docs.astral.sh/uv/)
- Pandoc (for rendering)
- LaTeX engine (xelatex) for PDF output

macOS (Homebrew):
```bash
brew install pandoc mactex-no-gui
eval "$(/usr/libexec/path_helper)"
```

```bash
uv sync --frozen
uv run cvw --help
uv run cvw validate --sot-path ./sot.sample
uv run cvw render --canonical runs/<timestamp>/canonical.md --format html,docx
```

## SoT layout

Provide a private SoT directory (not tracked in git). Example data lives in
`sot.sample/` and is safe to share.

## Outputs

Build artifacts are written under `dist/` and `runs/` and are always ignored by
git. Each run includes a canonical markdown file and a `resume.json` artifact.
Use `cvw sync` to push selected outputs into your site repo.

Variants can target multiple document types (resume, cover-letter). Tag filters
apply consistently to bullets and cover-letter sections.

## Dependency management

- Locked install (recommended): `uv sync --frozen`
- Update dependencies: `uv lock` then `uv sync`

Note: uv uses `--frozen` for locked installs (it will not modify `uv.lock`).

## Repo structure

- `config/`: global config and variants
- `build/`: templates, filters, styles, scripts
- `docs/`: architecture, site contract, security
- `sot.sample/`: fake data for tests and examples
- `src/`: CLI and core logic

## License

MIT
