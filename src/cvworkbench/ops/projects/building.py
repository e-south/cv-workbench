"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/ops/projects/building.py

Complete project builds and tailored source copies before retaining a run.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import shutil
import stat
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from cvworkbench.build.pipeline import BuildResult, execute_build
from cvworkbench.build.planning import plan_build
from cvworkbench.build.runs import allocate_run
from cvworkbench.config import ConfigSource, read_config, resolve_runs_path, resolve_sot_path
from cvworkbench.inputs.sot_versions import resolve_active_sot_path
from cvworkbench.inputs.validation import validate_sot
from cvworkbench.ops.projects.identity import resolve_project_dir
from cvworkbench.ops.projects.manifest import load_project
from cvworkbench.ops.projects.preparation import prepare_project_sot
from cvworkbench.ops.projects.records import ProjectError
from cvworkbench.storage import replace_files_atomically


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
        staged_run = Path(temporary) / "run"
        if prepared != source:
            staged_run.mkdir()
            retained_source = staged_run / "sot"
            shutil.move(str(prepared), retained_source)
            build_plan = replace(build_plan, sot_path=retained_source)
        result = execute_build(build_plan, run_dir=staged_run, dist_dir=staged_run)
        run_dir = _retain_run(staged_run, runs_root)
        return replace(
            result, run_dir=run_dir, dist_dir=run_dir, canonical_path=run_dir / "canonical.md"
        )


def _retain_run(staged_run: Path, runs_root: Path) -> Path:
    """Commit completed documents and their prepared source as one recoverable group."""
    payloads = [
        (path.relative_to(staged_run), path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
        for path in sorted(staged_run.rglob("*"))
        if path.is_file()
    ]
    directories = {
        path.relative_to(staged_run): stat.S_IMODE(path.stat().st_mode)
        for path in staged_run.rglob("*")
        if path.is_dir()
    }
    with allocate_run(runs_root) as run_dir:
        writes = [(run_dir / relative, content) for relative, content, _ in payloads]
        writes.sort(key=lambda write: write[0].name == "manifest.json")
        replace_files_atomically(
            writes,
            file_modes={run_dir / relative: mode for relative, _, mode in payloads},
            new_directories={run_dir / relative: mode for relative, mode in directories.items()},
            expected_contents={path: None for path, _ in writes},
        )
    return run_dir
