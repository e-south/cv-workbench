---
id: howto-performance
intent: Provide reproducible performance-profiling procedures.
audience: [maintainer, agent]
status: active
navigation:
  parent: ../readme.md
---

# Performance profiling

Profile deterministic commands, not ad hoc interactive runs. Pin the SoT,
variant, and output shape so before/after comparisons stay meaningful.

## Fast baseline commands

Build-only markdown path:

```bash
uv run python -m cProfile -o build.prof -m cvworkbench.cli build \
  --sot-path ./sot.sample \
  --variant base \
  --format md
```

One-shot preview render path:

```bash
uv run python -m cProfile -o preview-once.prof -m cvworkbench.cli preview \
  --sot-path ./sot.sample \
  --variant base \
  --once
```

Compact automation/bootstrap read path:

```bash
uv run python -m cProfile -o context.prof -m cvworkbench.cli context \
  --json \
  --compact
```

Project read path:

```bash
uv run python -m cProfile -o project-show.prof -m cvworkbench.cli project show \
  <project-id> \
  --json
```

## Noninteractive hotspot inspection

Use `pstats` directly when you want an interactive shell:

```bash
uv run python -m pstats build.prof
```

Or print the hottest frames noninteractively for logs and diffs:

```bash
uv run python -c "import pstats; s = pstats.Stats('build.prof'); s.sort_stats('cumtime'); s.print_stats(20)"
```

## What to compare

- `build --format md`: parser, selection, manifest, and render-planning overhead
- `preview --once`: default HTML-only render path; add `--with-pdf` when you
  want the extra PDF subprocess cost in the profile
- `context --json --compact`: workspace scan and run-catalog read cost
- `project show --json`: project metadata plus latest project-run resolution cost

Keep the workspace stable between runs. If you are profiling read paths such as
`context` or `project show`, note the approximate number of run manifests in
`var/runs/` because catalog size can dominate the result.
