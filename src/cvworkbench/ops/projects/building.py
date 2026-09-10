"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/building.py

Validate project builds in temporary source copies before allocating retained runs.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from cvworkbench.build.pipeline import BuildResult, create_run_dir, execute_build
from cvworkbench.build.planning import plan_build
from cvworkbench.config import ConfigSource, read_config, resolve_runs_path, resolve_sot_path
from cvworkbench.inputs.sot_versions import resolve_active_sot_path
from cvworkbench.inputs.validation import validate_sot
from cvworkbench.ops.projects.identity import resolve_project_dir
from cvworkbench.ops.projects.manifest import load_project
from cvworkbench.ops.projects.preparation import prepare_project_sot
from cvworkbench.ops.projects.records import ProjectError


class ProjectBuildError(ProjectError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(errors))


def build_project(
    project: str | Path,
    *,
    config_path: ConfigSource,
    sot_path: Path | None = None,
    formats: list[str] | None = None,
    theme: str | None = None,
    style_preset: str | None = None,
) -> BuildResult:
    """Build the selected proposal without changing source or project inputs."""
    configuration = read_config(config_path)
    spec = load_project(resolve_project_dir(project, configuration))
    source = (
        resolve_sot_path(sot_path, configuration)
        if sot_path is not None
        else resolve_active_sot_path(spec.sot_path)
    )
    runs_root = resolve_runs_path(configuration) / "projects" / spec.project_id
    with TemporaryDirectory(prefix="cvw-project-build-") as temporary:
        prepared = prepare_project_sot(
            project_dir=spec.project_dir, sot_path=source, target_dir=Path(temporary) / "sot"
        )
        errors = validate_sot(prepared)
        if errors:
            raise ProjectBuildError(errors)
        build_plan = plan_build(
            sot_path=prepared,
            config_path=configuration,
            variant_id=None,
            formats=formats,
            theme=theme,
            style_preset=style_preset,
            variant_path_override=spec.variant_path,
        )
        run_dir = create_run_dir(runs_root)
        if prepared != source:
            retained_source = run_dir / "sot"
            shutil.move(str(prepared), retained_source)
            build_plan = replace(build_plan, sot_path=retained_source)
        return execute_build(build_plan, run_dir=run_dir, dist_dir=run_dir)
