"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/pipeline.py

Builds document outputs from Source of Truth data.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cvworkbench.build.artifacts import artifact_paths, write_build_artifacts
from cvworkbench.build.planning import BuildPlan, plan_build
from cvworkbench.config import (
    ConfigSource,
    resolve_dist_path,
    resolve_runs_path,
)
from cvworkbench.storage import replace_files_atomically
from cvworkbench.variants import Variant


@dataclass(frozen=True)
class BuildResult:
    variant: Variant
    formats: list[str]
    canonical_path: Path
    dist_dir: Path
    run_dir: Path
    theme_id: str | None
    style_preset: str | None


def build_documents(
    *,
    sot_path: Path,
    config_path: ConfigSource,
    variant_id: str | None,
    formats: list[str] | None,
    theme: str | None = None,
    style_preset: str | None = None,
    variant_path_override: Path | None = None,
    run_dir: Path | None = None,
    dist_dir: Path | None = None,
    write_audit_artifacts: bool = True,
) -> BuildResult:
    build_plan = plan_build(
        sot_path=sot_path,
        config_path=config_path,
        variant_id=variant_id,
        formats=formats,
        theme=theme,
        style_preset=style_preset,
        variant_path_override=variant_path_override,
    )
    return execute_build(
        build_plan,
        run_dir=run_dir,
        dist_dir=dist_dir,
        write_audit_artifacts=write_audit_artifacts,
    )


def execute_build(
    build_plan: BuildPlan,
    *,
    run_dir: Path | None = None,
    dist_dir: Path | None = None,
    write_audit_artifacts: bool = True,
) -> BuildResult:
    """Materialize a complete bundle before recoverable replacement of owned files."""
    build_plan.render_assets.verify(build_plan.filter_paths, build_plan.render_plans)
    configuration = build_plan.configuration
    dist_dir = dist_dir or (resolve_dist_path(configuration) / build_plan.variant.id)
    destinations = artifact_paths(
        build_plan,
        run_dir=run_dir,
        dist_dir=dist_dir,
        write_audit_artifacts=write_audit_artifacts,
    )
    expected: dict[Path, bytes | None] = {}
    for path in destinations.values():
        try:
            expected[path] = path.read_bytes()
        except FileNotFoundError:
            expected[path] = None

    with TemporaryDirectory(prefix="cvw-build-") as temporary:
        stage_root = Path(temporary)
        stage_run = stage_root / "run"
        shared = run_dir is not None and run_dir.resolve() == dist_dir.resolve()
        stage_dist = stage_run if shared else stage_root / "dist"
        staged = artifact_paths(
            build_plan,
            run_dir=stage_run,
            dist_dir=stage_dist,
            write_audit_artifacts=write_audit_artifacts,
        )
        write_build_artifacts(
            build_plan,
            run_dir=stage_run,
            dist_dir=stage_dist,
            write_audit_artifacts=write_audit_artifacts,
        )
        build_plan.render_assets.verify(build_plan.filter_paths, build_plan.render_plans)
        # Capture completed payloads before reserving a persistent run.
        contents = {key: path.read_bytes() for key, path in staged.items()}
        allocated = run_dir is None
        run_identity = None
        if run_dir is None:
            run_dir = create_run_dir(resolve_runs_path(configuration))
            identity = run_dir.lstat()
            run_identity = (identity.st_dev, identity.st_ino)
        try:
            if allocated:
                destinations = artifact_paths(
                    build_plan,
                    run_dir=run_dir,
                    dist_dir=dist_dir,
                    write_audit_artifacts=write_audit_artifacts,
                )
                for (scope, _), path in destinations.items():
                    if scope == "run":
                        expected[path] = None
            writes: dict[Path, tuple[Path, bytes]] = {}
            for key, path in destinations.items():
                writes[path.resolve()] = (path, contents[key])
            # Metadata follows document writes; recovery covers the entire group.
            ordered = sorted(writes.values(), key=lambda write: write[0].name == "manifest.json")
            replace_files_atomically(
                ordered,
                expected_contents={path: expected[path] for path, _ in ordered},
            )
        except BaseException as exc:
            if allocated:
                try:
                    current = run_dir.lstat()
                    if (current.st_dev, current.st_ino) == run_identity:
                        run_dir.rmdir()
                    else:
                        exc.add_note(f"Build run replaced during commit; preserved: {run_dir}")
                except OSError:
                    exc.add_note(f"Build run retained for inspection: {run_dir}")
            raise

    return BuildResult(
        variant=build_plan.variant,
        formats=build_plan.formats,
        canonical_path=run_dir / "canonical.md",
        dist_dir=dist_dir,
        run_dir=run_dir,
        theme_id=build_plan.theme.id,
        style_preset=build_plan.style_preset,
    )


def create_run_dir(runs_root: Path) -> Path:
    base_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    runs_root.mkdir(parents=True, exist_ok=True)

    for suffix in range(0, 1000):
        name = base_timestamp if suffix == 0 else f"{base_timestamp}-{suffix:02d}"
        run_dir = runs_root / name
        try:
            run_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            continue
        return run_dir

    raise RuntimeError(f"Could not allocate unique run directory for timestamp: {base_timestamp}")
