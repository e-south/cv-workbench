"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/resources.py

Resolves immutable distribution data shared by installed and editable runtimes.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def distribution_path(name: str) -> Path:
    """Return a data directory from an unpacked wheel or editable installation."""
    try:
        resource = files("cvworkbench_data").joinpath(name)
    except ModuleNotFoundError as exc:
        raise FileNotFoundError(
            "Distribution resources are missing; reinstall cv-workbench "
            "(checkout: uv sync --reinstall-package cv-workbench)."
        ) from exc
    if not isinstance(resource, Path) or not resource.is_dir():
        raise FileNotFoundError(f"Installed cv-workbench resource directory is missing: {name}")
    return resource
