# Performance profiling

Use `cProfile` to capture CLI performance for a single command run.

```bash
uv run python -m cProfile -o build.prof -m cvworkbench.cli build \
  --sot-path ./sot.sample \
  --variant base \
  --format md
```

Inspect the hottest functions with `pstats`:

```bash
uv run python -m pstats build.prof
```

Inside the `pstats` shell:

```
sort cumtime
stats 20
```

Keep runs deterministic by pinning inputs and formats in the command line.
