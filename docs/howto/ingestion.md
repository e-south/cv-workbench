# Ingestion

The ingestion pipeline turns a URL (or any text-based context source) into a
local registry entry with deterministic signals and a draft variant strategy.

## Add a context URL

```bash
uv run cvw job add --url https://example.com/context
```

This command:
- Fetches and extracts readable text from the URL.
- Stores source metadata and extracted markdown.
- Generates deterministic signals and a draft `strategy.yaml`.

## Registry layout

Entries live under the registry path configured in `config/workbench.yaml`
(default: `../var/registry`):

```
var/registry/
  contexts/
    context-<hash>/
      source.json
      extracted.md
      signals.json
      strategy.yaml
```

The context id is derived from a stable hash of the URL. If the context already
exists, ingestion fails fast with an error so you can decide whether to delete
or rename the existing entry.

## Project ingestion (job tailoring)

Use a project when you want job-specific artifacts and proposals:

```bash
uv run cvw project new --job-url https://example.com/job --variant base
```

Projects store extracted text and signals by default. Raw HTML is opt-in:

```bash
uv run cvw project new --job-url https://example.com/job --variant base --store-raw
```

If you prefer a local file:

```bash
uv run cvw project new --job-file ./job.txt --variant base
```

Project proposals are ephemeral. Promote or discard them explicitly:

```bash
uv run cvw variant inbox
uv run cvw variant keep --project <slug> --id <variant-id>
uv run cvw variant discard --project <slug> --yes
```

New projects scaffold a project-local proposal variant plus a `project-ops`
patch file at `proposals/patch.yaml`. `project guide` helps you choose a base
variant and inspect signals; it does not directly rewrite SoT content.

Today the supported executable op families are guarded experience bullet
replacement and project summary replacement. Use
`uv run cvw project patch replace-experience-bullet <slug> ...` or
`uv run cvw project patch replace-project-summary <slug> ...` to append
validated ops without hand-editing YAML. The commands record stable ids plus
the expected source text so project preview, build, and apply fail fast if the
underlying SoT has drifted.

## Configuration

The registry path and user agent are set in `config/workbench.yaml`:

```yaml
paths:
  registry: ../var/registry
registry:
  user_agent: cv-workbench/0.1
```

## Tips

- Ingestion is generic. Use it for job listings, product pages, blog posts, or
  any context you want to mine for signals.
- If a site blocks automated access, the command will fail instead of silently
  falling back. Capture the text manually and store it in your private SoT if
  needed.
