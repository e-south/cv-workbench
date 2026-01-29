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
uv sync --locked
uv run cvw --help
uv run cvw doctor
uv run cvw init
uv run cvw quickstart
uv run cvw validate --sot-path ./sot.sample
uv run cvw build --sot-path ./sot.sample --variant base --format md,pdf
```

Build output locations are printed after `cvw build` completes, and artifacts
are written under `dist/<variant>/` (configurable via `config/workbench.yaml`).

Local sync is the default. Use `--mode pr` explicitly to open a PR in your site
repo.

To ingest a job or other context URL:
```bash
uv run cvw job add --url https://example.com/job
```

To generate a review bundle and import DOCX edits as a patch proposal:
```bash
uv run cvw reviewpack --variant base
uv run cvw import-docx --from reviews/base/cv.docx
```

## SoT layout

Provide a private SoT directory (not tracked in git). Example data lives in
`sot.sample/` and is safe to share.

Optional sections supported when present in the SoT directory:
`publications.yaml`, `honors.yaml`, `service.yaml`, `teaching.yaml`,
`conferences.yaml`, and `references.yaml`.

Snippets are optional, scoped markdown blocks that override or introduce
content. Provide `snippets.yaml` with entries that point to files under
`snippets/` (for example `snippets/summary.md`, `snippets/experience.md`).
Supported scopes: `summary`, `section-intro`, `letter-open`, `letter-close`.

Example `snippets.yaml`:
```yaml
snippets:
  - id: summary
    scope: summary
    path: snippets/summary.md
  - id: experience-intro
    scope: section-intro
    section: experience
    path: snippets/experience.md
```

Tags are normalized (case/punctuation-insensitive). Namespaced tags such as
`domain:synthetic-biology` also register the namespace tag (`domain`) for
broader include/exclude rules.

Publication author roles are marked during rendering via
`build/filters/author_roles.lua` (co-first `*`, corresponding `†`, senior `‡`).

Paths in `config/workbench.yaml` are resolved relative to the config file
location (for example, `../dist` is relative to `config/`).

## Outputs

Build artifacts are written under `dist/` and `runs/` and are always ignored by
git. Each run includes a canonical markdown file and a `resume.json` artifact.
Use `cvw sync` to push selected outputs into your site repo.

Variants can target multiple document types (resume, cover-letter). Tag filters
apply consistently to bullets and cover-letter sections.

Publishable variants are gated by `config/publish.yaml`. Sync refuses to publish
variants not listed there.

## Dependency management

- Locked install (recommended): `uv sync --locked`
- Update dependencies: `uv lock` then `uv sync`

## Repo structure

- `config/`: global config and variants
- `registry/`: local context registry for ingested URLs (ignored by git)
- `reviews/`: review packs (DOCX/PDF + checklist, ignored by git)
- `build/`: templates, filters, styles, scripts
- `docs/`: concepts, how-to guides, reference, and plans
- `sot.sample/`: fake data for tests and examples
- `src/`: CLI and core logic

## License

MIT
