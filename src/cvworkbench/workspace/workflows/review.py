"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/workflows/review.py

Describe review workflow preconditions, commands, outputs, and stop conditions.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from cvworkbench.workspace.commands import command_prefix, recipe_command


def review_import_recipe(
    *, config_path: Path, sot_path: Path | None, configured_sot_path: str | None, variant_label: str
) -> dict[str, Any]:
    return {
        "id": "review.import",
        "title": "Review and import DOCX edits",
        "preconditions": [
            "runs.latest_by_variant includes the target variant",
            "the selected run includes immutable cv.docx, cv.pdf, and selection.json artifacts",
        ],
        "steps": [
            {
                "command": recipe_command(
                    f"reviewpack --variant {variant_label}",
                    config_path=config_path,
                    sot_path=None,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Create a review pack with DOCX/PDF, checklist, and an exact source-run record.",
            },
            {
                "command": "edit var/reviews/<variant>/cv.docx",
                "description": "Apply manual edits to the DOCX review file.",
            },
            {
                "command": recipe_command(
                    f"import-docx --from var/reviews/{variant_label}/cv.docx "
                    f"--variant {variant_label}",
                    config_path=config_path,
                    sot_path=None,
                    configured_sot_path=configured_sot_path,
                ),
                "description": "Generate an import draft plus machine metadata describing whether patch.yaml or patch.diff is applyable to SoT.",
            },
            {
                "command": "edit var/drafts/import-*/notes.md",
                "description": "Review notes.md for operator context; draft.json is the authoritative apply_status record.",
            },
            {
                "command": shlex.join(
                    [
                        *command_prefix(),
                        "apply",
                        "--draft",
                        "<draft-dir>",
                        "--sot-path",
                        str((sot_path or Path("<path-to-sot>"))),
                    ]
                ),
                "description": "Apply the imported patch after explicit approval when draft.json reports apply_status: ready. If it reports ready_no_changes, no SoT mutation is needed.",
            },
        ],
        "outputs": [
            "var/reviews/<variant>/cv.docx",
            "var/reviews/<variant>/review-source.json",
            "var/drafts/import-*/patch.yaml",
            "var/drafts/import-*/patch.diff",
            "var/drafts/import-*/draft.json",
            "var/drafts/import-*/notes.md",
        ],
        "stop_conditions": [
            "If no runs exist, run the baseline build recipe first.",
            "Keep review-source.json beside the edited DOCX; a standalone file requires an explicit --run.",
            "Use reviewpack --run <run-id> when you need a pinned review pack in a multi-run workspace.",
            "If draft.json reports review_diff_only, author a real SoT patch manually instead of applying the draft patch payload.",
        ],
    }
