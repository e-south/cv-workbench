---
id: reference-project-inspection
intent: Define read-only project inspection APIs and their diagnostic boundaries.
audience: [agent, maintainer]
status: active
navigation:
  parent: project-contract.md
---

# Project inspection

`cvworkbench.workspace.projects` owns the shared inspection behind `project show`
and preview guidance. Project creation, mutation, and artifact parsing remain
in the [project operation owners](project-contract.md#python-ownership).

## Full inspection

```python
from pathlib import Path
from cvworkbench.workspace.projects import inspect_project

state = inspect_project("research", config=Path("config/workbench.yaml"))
```

The selector accepts a project ID or directory path. The returned dictionary
contains the project, proposal, job, signals, patch, latest project-run review
state, available command descriptions, stored-file observations, and optional
saved guidance. It is the `project show --json` payload without the CLI's
`command` envelope. Inspection prints nothing, executes no suggested commands,
and writes no workspace files.

One call captures one workbench configuration generation for project resolution,
run lookup, proposal-ID suggestions, and saved-guidance comparisons. `config`
also accepts an explicit `ConfigSnapshot`. A later path-based call captures
updated settings. This does not capture all project, source, variant, or run
files atomically; see [configuration lifetime](configuration-contract.md).

Invalid project metadata raises `ProjectError`. Configuration failures remain
filesystem errors or `ValueError` for Python callers. The CLI reports these
errors on stderr, exits with code 1, and emits no partial JSON. Malformed optional
saved guidance appears as a
diagnostic in an otherwise available inspection. An absent plan leaves the
remaining observations available without a plan diagnostic.

### Proposal availability and retained history

Proposal files are ephemeral; retained project metadata, job context, saved
guidance, and run history do not depend on their presence. `proposal.status` is
`available` when both proposal files can be loaded, or `unavailable` otherwise.
`proposal.issues` records each affected `artifact` (`variant` or `patch`), its
`state` (`missing`, `unreadable`, or `invalid`), and an `error` without parser
source excerpts. `proposal_warning` explains which actions require restoration.
Inspection checks that each input is a regular file inside its project before
reading it. This check does not lock out concurrent filesystem changes.

Unavailable variant fields are null. An unavailable patch has null `format`,
`is_empty`, `line_count`, and `operations`, with `status: unavailable`; it is
never described as an empty patch. Available fields, job-file observations, and
saved-plan comparisons remain visible when another proposal input is unavailable.
Availability establishes parseable proposal inputs, not source compatibility,
successful compilation, or human approval.

An unavailable proposal's `commands` contains `show` and, when a retained run
has review inputs, its pinned `reviewpack`. It omits preview, build, apply, keep,
and discard suggestions. `review.next_command` is null when neither building
nor reviewing is available. The [content-review contract](review-contract.md)
separates packaging a retained run from importing edits against current inputs.

## Preview inspection

```python
from pathlib import Path
from cvworkbench.workspace.projects import inspect_project_preview

guidance = inspect_project_preview(
    Path("var/projects/research"), config=Path("config/workbench.yaml")
)
```

This API takes a resolved project directory. Both optional arguments may be
omitted; `config` accepts a path or snapshot, and `sot_path` selects the source
used for guidance comparison. The result projects the same patch visibility,
artifact status, and saved-guidance observations into compact preview fields.
It omits detailed job-file records, command descriptions, and run review state;
it does not scan run history or allocate a suggested proposal identity.

Invalid project metadata produces `project_id` and `project_context_error`.
Unavailable proposal inputs retain the remaining observations, with
`proposal_status` and `proposal_warning`. The warning appears as text in the
preview's project warning area. Preview startup and rebuild still enforce
executable inputs; these observations do not enable an unavailable build.
Unavailable configuration leaves the other observations visible and records
unverifiable guidance inputs. Missing optional guidance is distinct from invalid
guidance. The preview controller caches these observations at its last successful
build; the API itself has no cache. See [guidance provenance](guidance-provenance.md)
for comparison states and [preview behavior](preview-contract.md).

## Ownership

| Responsibility beneath `workspace/projects/` | Owner |
| --- | --- |
| Project summaries and workspace inventory | `inventory.py` |
| Full and preview inspection composition | `inspection.py` |
| Descriptions of available project commands | `commands.py` |
| Observation labels, warnings, and recommendation summaries | `guidance.py` |

The package entrypoint exports these APIs explicitly. Internal modules import
their concrete owners. CLI and preview adapters call inspection; workspace
modules do not import those adapters or terminal libraries. Verification lives
in `tests/workspace/projects/`, the architecture-boundary tests, and the CLI
and preview suites.
