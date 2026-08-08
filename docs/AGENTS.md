# Documentation rules

- Start at `docs/readme.md`; open only the concept, how-to, or reference leaf needed for the task.
- Live documents under `concepts/`, `howto/`, and `reference/` follow `reference/documentation-contract.md` frontmatter and progressive disclosure rules.
- Keep one semantic owner per contract. Route with links instead of duplicating command lists, security policy, or lifecycle semantics.
- Treat `plans/`, `dev/`, and `reference/journal.md` as historical context, not current operational authority.
- When code behavior changes, update the owning leaf and the repository-contract tests together.
