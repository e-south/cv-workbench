# Ingestion

Use `project guide` or `project new` for the main job-tailoring workflow. Those
commands create a project-local proposal, signals, and patch scaffold. Use
`job add` when you want the generic registry path without creating a project.

The ingestion pipeline turns a URL (or any text-based context source) into
deterministic local artifacts.

## Generic Context Ingestion

```bash
uv run cvw job add --url https://example.com/context
```

This command:
- Fetches and extracts readable text from the URL.
- Stores source metadata and extracted markdown.
- Generates deterministic signals and a draft `strategy.yaml`.
- Rejects non-public or non-`https` URLs; save local or internal content to a
  file and use `--job-file` instead.

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
variant, auto-applies the top eligible recommendation when `--variant` is
omitted, writes `job/proposal-plan.json` with deterministic ranking rationale
and evidence snippets, and does not directly rewrite SoT content. If you pass
`--variant`, that explicit scaffold lane is preserved.

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
- URL ingestion is intentionally strict: only public `https` targets are
  accepted. Loopback, RFC1918/private, link-local, localhost, and non-default
  ports fail fast.
- Registry ids are keyed from the exact URL string. If a job board adds
  tracking query params and you want stable dedupe, prefer the canonical
  listing URL or save the text locally and use `--job-file`.
- If a site blocks automated access, the command will fail instead of silently
  falling back. Capture the text manually and store it in your private SoT if
  needed.
