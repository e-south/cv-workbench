"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/workspace/publication.py

Describes the authored publication journey from observed state, without CLI coupling.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

from cvworkbench.config import resolve_publication_variant
from cvworkbench.ops.publication.state import PublicationState, inspect_publication


def inspect_workspace_publication(
    config_path: Path, *, sot_path: Path | None = None
) -> PublicationState:
    try:
        variant = resolve_publication_variant(config_path)
    except (ValueError, OSError) as exc:
        return PublicationState(variant="", reasons=(str(exc),))
    return inspect_publication(config_path, variant, sot_path=sot_path)


def publication_recipe(
    state: PublicationState,
    *,
    config_path: Path,
    command_prefix: list[str],
    sot_path: Path | None = None,
) -> dict[str, Any]:
    steps = []

    def command(argv: list[str], description: str, *, sync: bool = False) -> None:
        tokens = [*command_prefix, *argv, "--config", str(config_path)]
        if sync:
            tokens.extend(["--site-config", str(config_path.parent / "site-sync.yaml")])
        else:
            tokens.extend(["--variant", state.variant or "<publication-variant>"])
            if sot_path is not None:
                tokens.extend(["--sot-path", str(sot_path)])
        value = shlex.join(tokens)
        placeholders = re.findall(r"<[^>]+>", value)
        steps.append(
            {
                "command": value,
                "description": description,
                "kind": "command",
                "runnable": not placeholders,
                "placeholders": placeholders,
            }
        )

    command(
        ["publication", "status", "--json"],
        "Inspect authored source, export, artifact and review freshness.",
    )
    if state.state not in {"review_required", "reviewed"}:
        command(
            [
                "prepare-public-pdf",
                "--authored-source",
                state.authored_source or "<authored-source.docx>",
                "--source-pdf",
                state.exported_pdf or "<exported-source.pdf>",
            ],
            "Export current DOCX changes locally before preparing the faithful public PDF.",
        )
    if state.state != "reviewed":
        steps.append(
            {
                "command": "Review "
                + (
                    state.review_path
                    if state.state == "review_required"
                    else "the packet path printed by preparation"
                ),
                "description": "Check header alignment, links, disclosure, line wraps and page breaks; preparation does not declare review.",
                "kind": "manual",
                "runnable": False,
                "placeholders": [],
            }
        )
        digest = state.pdf_sha256 if state.state == "review_required" else "<prepared-pdf-sha256>"
        command(
            ["publication", "review", "--pdf-sha256", digest],
            "Record review of the exact hash shown in the current packet.",
        )
    command(
        ["sync", "--mode", "local"],
        "Sync only after current-source and exact-PDF review checks pass.",
        sync=True,
    )
    return {
        "id": "authored.publish",
        "title": "Prepare, review and publish the authored CV",
        "preconditions": [
            "Explicit authored DOCX and local PDF export.",
            "Configured disclosure policy, approved graphics fingerprint and site destination.",
        ],
        "steps": steps,
        "outputs": [
            "Prepared public PDF and local visual packet.",
            "Private preparation and review records.",
            "Validated PDF and sanitized manifest at the configured site.",
        ],
        "stop_conditions": [
            "Do not infer a source path or review approval.",
            "Stop at the manual review step until the exact PDF has been inspected.",
            "Re-export after DOCX changes; re-prepare and review after input or packet changes.",
        ],
    }
