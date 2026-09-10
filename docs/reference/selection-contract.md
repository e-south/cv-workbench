---
id: reference-selection-contract
intent: Define document-specific selection evidence and how explanation and review consume it.
audience: [operator, agent, maintainer]
status: active
navigation:
  parent: ../readme.md
---

# Selection evidence

`build/selection.py` owns `selection.json`: tag and bullet-limit decisions made
from the build's captured source and variant. A retained run keeps its original
selection evidence; rebuilding replaces the variant's dist copy. Use `explain
--run <run-id> --id <item-id>` to inspect a retained build, or `explain --variant
<variant-id> --id <item-id>` for the latest dist copy. `--selection` accepts an
explicit file and `--json` returns machine-readable results.

## Cover letters

The payload names `document_type: cover-letter` and the selected `letter_id`.
Its `items` contain only that letter's sections, in source order. Each item has:

- the normalized section `id`, `type: section`, and `section: letters`;
- its owning `letter_id`, source `text`, and optional heading as `label`;
- normalized `tags`, an `included` boolean, and exclusion `reasons`.

Excluded sections remain inspectable. An exclude-tag match wins over an include
match; otherwise a nonempty include set requires a matching tag. Reasons use
`exclude_tag:<tag>` or `missing_include`, consistent with rendering. The existing
`max_bullets_per_role` envelope field remains for compatibility and does not
limit letter paragraphs. Other letters and resume entries do not appear in this
document's selection evidence.

Rendering and selection use `build/selection.py::select_letter` to resolve the
same requested letter. A missing `letter_id` or absent letter raises an error
before build artifacts are allocated. Full source-schema validation retains
its [existing owner](configuration-contract.md#build-and-render-boundaries).

Selection is an account of filterable source sections, not an inventory of every
rendered element. Contact lines, title, salutation, closing, and opening/closing
snippets are not section items. This evidence does not establish editing
eligibility, source freshness, factual accuracy, or publication approval.

## Consumers and compatibility

`explain --type section --id <section-id>` displays the letter identity, text,
tags, and decision. `reviewpack` includes selected letter sections in its
checklist and omits excluded sections. It uses the retained run's evidence;
current source edits do not rewrite an older checklist's baseline.

Resume selection payloads and bullet checklists retain their existing format.
Historical cover-letter runs made before document-specific selection may contain
resume entries; this change does not rewrite their evidence. Rebuild and create
a new review pack to obtain letter-specific explanations and checklist items.

Cover-letter DOCX imports remain `review_diff_only`; this change does not add
executable letter patches. See [content review](review-contract.md#import-outputs)
and the [cover-letter workflow](../howto/quickstart.md#cover-letter-workflow).
`tests/build/test_selection.py` checks real CLI build/explain/review behavior,
rendered tag-filter parity, selection of one letter, and missing-authority errors.
