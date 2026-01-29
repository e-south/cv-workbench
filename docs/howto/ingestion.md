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
(default: `../registry`):

```
registry/
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

## Configuration

The registry path and user agent are set in `config/workbench.yaml`:

```yaml
paths:
  registry: ../registry
registry:
  user_agent: cv-workbench/0.1
```

## Tips

- Ingestion is generic. Use it for job listings, product pages, blog posts, or
  any context you want to mine for signals.
- If a site blocks automated access, the command will fail instead of silently
  falling back. Capture the text manually and store it in your private SoT if
  needed.
