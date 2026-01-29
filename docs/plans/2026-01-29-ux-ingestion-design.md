# UX + Ingestion Design (2026-01-29)

## Goal

Improve the top-level CLI experience with local-first defaults and add a
low-friction URL ingestion pipeline that produces deterministic signals and
draft variant strategy without mutating the SoT.

## UX Surface

Top-level commands remain the primary interface:

- init
- quickstart
- doctor
- validate
- build
- render
- tailor
- diff
- sync
- apply
- job add (URL ingestion)

Local operations are first-class. Sync defaults to local and PR sync is opt-in.
Every command prints explicit artifact paths. Rich output is the default, with
plain/json modes for agents and CI.

## URL Ingestion Flow

`cvw job add --url <url>`:

1) Fetch URL and extract main content via Trafilatura.
2) Create a registry entry under `registry/contexts/context-<hash>/`.
3) Write:
   - `source.json` (URL, retrieved timestamp, extractor version, title)
   - `extracted.md` (cleaned text)
   - `signals.json` (deterministic keywords/tags)
   - `strategy.yaml` (draft variant strategy)

Raw HTML is not stored by default. The registry is local-only and ignored by git.

## Registry Layout

```
registry/
  contexts/
    context-<hash>/
      source.json
      extracted.md
      signals.json
      strategy.yaml
```

Context IDs are privacy-preserving (`context-<hash>`). Human labels are stored
only in metadata.

## Deterministic Signals

Signals are computed without LLMs for auditability:

- normalized keywords (token frequency)
- word count
- suggested tag candidates (namespaced if possible)

These feed `strategy.yaml` as draft include/exclude suggestions.

## Publish Gating

`config/publish.yaml` defines which variants can be synced to public targets.
Sync errors if the publish variant is not allowed.

## Error Handling

Commands fail fast with actionable messages:

- URL fetch errors (status/content type)
- empty extraction
- missing runtime dependencies

## Tests

- CLI tests for init/quickstart/doctor/job add
- Ingestion unit tests (mocked fetch/extract)
- Signals and strategy generation tests
- Publish gating enforcement tests

