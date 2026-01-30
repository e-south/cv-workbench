"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/paths.py

Resolves internal paths used by the workbench.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from cvworkbench.variants import Variant


def filters_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "build" / "filters"


def output_path(dist_dir: Path, variant: Variant, fmt: str) -> Path:
    if fmt == "ats":
        filename = f"{variant.output_name}.ats.txt"
    else:
        extension = "md" if fmt == "md" else fmt
        filename = f"{variant.output_name}.{extension}"
    return dist_dir / filename
