"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/formats.py

Normalizes output-format selections for build and render workflows.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from collections.abc import Sequence


def normalize_output_formats(formats: Sequence[str] | None) -> list[str] | None:
    if not formats:
        return None

    normalized: list[str] = []
    seen: set[str] = set()
    for value in formats:
        stripped = value.strip()
        if not stripped or stripped in seen:
            continue
        normalized.append(stripped)
        seen.add(stripped)
    return normalized
