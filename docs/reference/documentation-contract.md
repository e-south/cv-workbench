---
id: reference-documentation-contract
intent: Define durable documentation metadata, routing, and lifecycle rules.
audience: [agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Documentation Contract

The documentation tree is organized by reader intent:

- `docs/readme.md` is the router. It should answer “where do I go next?” rather than repeat leaf guidance.
- `concepts/` owns architecture, boundaries, and system vocabulary.
- `howto/` owns executable operator journeys.
- `reference/` owns stable contracts and exact behavior.
- `plans/` and `dev/` are historical or working records; they are not runtime instructions.

## Frontmatter

Live concept, how-to, and reference documents declare:

- `id`: stable, unique semantic identity.
- `intent`: one sentence describing the question the document answers.
- `audience`: the readers expected to act on it.
- `status`: `active` for authoritative guidance or `historical` for retained context.
- `navigation.parent`: the next broader routing surface.

Keep operational instructions in the closest authoritative leaf. Link from broader documents instead of copying command lists or policy prose.

## Progressive disclosure

Agents start with root `AGENTS.md`, run `uv run cvw context --json`, and open only the document selected by its recipe or by `docs/readme.md`. Code-area instructions live in scoped `AGENTS.md` files. Historical plans are consulted only when the live contract does not explain a decision.

When implementation behavior changes, update the owning leaf and its tests in the same change. Do not preserve competing descriptions of the same contract.
