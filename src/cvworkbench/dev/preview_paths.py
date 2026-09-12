"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/dev/preview_paths.py

Owns invocation-scoped preview input and rendered-output locations.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from cvworkbench.config import ConfigSource, resolve_runs_path
from cvworkbench.ops.projects.identity import validate_project_id
from cvworkbench.variants import validate_variant_id


@dataclass(frozen=True)
class PreviewPaths:
    root: Path

    @property
    def input_dir(self) -> Path:
        return self.root / "input"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"


def resolve_preview_paths(
    config_path: ConfigSource,
    *,
    preview_id: UUID,
    variant_id: str,
    project_id: str | None = None,
) -> PreviewPaths:
    """Resolve without writes; preview identity is independent of a browser lease."""
    if project_id is not None:
        validate_project_id(project_id)
        scope, subject = "projects", project_id
    else:
        validate_variant_id(variant_id)
        scope, subject = "variants", variant_id
    root = resolve_runs_path(config_path) / "preview" / scope / subject / preview_id.hex
    return PreviewPaths(root=root)
