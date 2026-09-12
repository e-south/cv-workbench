"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/build/artifacts.py

Defines bundle members and materializes completed artifacts in caller-owned staging.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import copy
import shutil
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from cvworkbench.build.manifest import build_manifest, collect_manifest_metadata, write_manifest
from cvworkbench.build.paths import output_path
from cvworkbench.build.planning import BuildPlan
from cvworkbench.build.rendering import RenderRequest, render_documents
from cvworkbench.build.resume import write_resume
from cvworkbench.build.styles import html_style_path, prepare_html_style


def artifact_paths(
    build_plan: BuildPlan,
    *,
    run_dir: Path | None,
    dist_dir: Path,
    write_audit_artifacts: bool,
) -> dict[tuple[str, str], Path]:
    """Enumerate only owned files, rejecting collisions between semantic roles."""
    paths: dict[tuple[str, str], Path] = {}
    if run_dir is not None:
        paths["run", "canonical"] = run_dir / "canonical.md"
        if write_audit_artifacts:
            paths["run", "resume"] = run_dir / "resume.json"
    if write_audit_artifacts:
        for scope, root in (("run", run_dir), ("dist", dist_dir)):
            if root is not None:
                for role in ("selection", "manifest"):
                    paths[scope, role] = root / f"{role}.json"
    for fmt in build_plan.formats:
        paths["dist", fmt] = output_path(dist_dir, build_plan.variant, fmt)
        if run_dir is not None and write_audit_artifacts:
            paths["run", fmt] = output_path(run_dir, build_plan.variant, fmt)
    html_plan = build_plan.render_plans.get("html")
    if html_plan and html_plan.style_kind == "css" and html_plan.style_path is not None:
        relative = html_style_path(build_plan.theme.id, build_plan.style_preset)
        paths["dist", "style"] = dist_dir / relative
        if run_dir is not None and write_audit_artifacts:
            paths["run", "style"] = run_dir / relative
    owners: dict[Path, str] = {}
    for (_, role), path in paths.items():
        if path.is_symlink():
            raise ValueError(f"Artifact destinations must not be symbolic links: {path}")
        resolved = path.resolve()
        if resolved in owners and owners[resolved] != role:
            raise ValueError(f"Artifact paths overlap: {path} ({owners[resolved]} and {role})")
        owners[resolved] = role
    return paths


def write_build_artifacts(
    build_plan: BuildPlan,
    *,
    run_dir: Path,
    dist_dir: Path,
    write_audit_artifacts: bool,
) -> None:
    """Render into isolated directories; callers own their lifetime and promotion."""
    configuration = build_plan.configuration
    variant = build_plan.variant
    selected_formats = build_plan.formats
    theme_obj = build_plan.theme
    preset = build_plan.style_preset
    selection_payload = build_plan.selection_payload
    canonical_path = run_dir / "canonical.md"
    run_dir.mkdir(parents=True, exist_ok=True)
    canonical_path.write_text(build_plan.markdown)
    resume_path: Path | None = None
    resume_content: bytes | None = None
    if write_audit_artifacts:
        resume_path = run_dir / "resume.json"
        write_resume(resume_path, build_plan.resume_payload)
        resume_content = resume_path.read_bytes()
        selection_path = run_dir / "selection.json"
        selection_path.write_text(selection_payload)

    dist_dir.mkdir(parents=True, exist_ok=True)
    if write_audit_artifacts:
        (dist_dir / "selection.json").write_text(selection_payload)

    output_paths: dict[str, Path] = {}
    render_details: dict[str, dict[str, str | None | list[str]]] = {}
    render_requests: list[RenderRequest] = []
    manifest_metadata_future: Future | None = None
    manifest_executor: ThreadPoolExecutor | None = None

    for fmt in selected_formats:
        output_file = output_path(dist_dir, variant, fmt)
        plan = build_plan.render_plans[fmt]
        if fmt == "html":
            plan = prepare_html_style(dist_dir, plan, theme_obj.id, preset)
            if write_audit_artifacts and plan.style_kind == "css" and plan.style_path:
                source_style = dist_dir / plan.style_path
                run_style = run_dir / plan.style_path
                if source_style != run_style:
                    run_style.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_style, run_style)
        render_requests.append(
            RenderRequest(
                input_path=canonical_path,
                output_path=output_file,
                variant=variant,
                filters_dir=build_plan.filters_path,
                output_format=fmt,
                pdf_engine=build_plan.pdf_engine,
                render_plan=plan,
            )
        )

    def _ensure_manifest_metadata_future() -> Future:
        nonlocal manifest_executor, manifest_metadata_future
        if manifest_metadata_future is not None:
            return manifest_metadata_future
        if resume_path is None or resume_content is None:
            raise RuntimeError("resume_path must be available when writing audit artifacts")
        manifest_executor = ThreadPoolExecutor(max_workers=1)
        manifest_metadata_future = manifest_executor.submit(
            collect_manifest_metadata,
            sot_hashes=build_plan.sot_hashes,
            snippet_hashes=build_plan.snippet_hashes,
            variant_hash=build_plan.variant_hash,
            resume_name=resume_path.name,
            resume_content=resume_content,
            pdf_engine=build_plan.pdf_engine,
            repo_root=configuration.path.parent.parent,
        )
        return manifest_metadata_future

    def _record_render_success(request: RenderRequest) -> None:
        if write_audit_artifacts:
            _ensure_manifest_metadata_future()
        output_file = request.output_path
        output_paths[request.output_format] = output_file
        if write_audit_artifacts:
            run_output = run_dir / output_file.name
            if output_file.resolve() != run_output.resolve():
                shutil.copy2(output_file, run_output)
            plan = request.render_plan
            if plan is None:
                raise RuntimeError("render_plan must be available when writing audit artifacts")
            render_details[request.output_format] = {
                "to": plan.to,
                "template": str(plan.template) if plan.template else None,
                "pdf_engine": plan.pdf_engine,
                "defaults": [str(path) for path in plan.defaults],
                "style_path": str(plan.style_path) if plan.style_path else None,
                "style_hash": plan.style_hash,
            }

    try:
        render_documents(
            render_requests,
            filter_paths=build_plan.filter_paths,
            after_each_success=_record_render_success,
        )
        if write_audit_artifacts:
            metadata_future = _ensure_manifest_metadata_future()
            dist_manifest = build_manifest(
                variant=variant,
                formats=selected_formats,
                output_paths=output_paths,
                metadata=metadata_future.result(),
                configuration_sha256=configuration.sha256,
                render={
                    "theme": theme_obj.id,
                    "theme_hash": build_plan.theme_hash,
                    "style_preset": preset,
                    "formats": render_details,
                    "filters": build_plan.render_assets.filter_metadata(),
                },
            )
            write_manifest(dist_dir / "manifest.json", dist_manifest)

            # Reuse the deterministic manifest payload so build metadata is computed once.
            run_manifest = copy.deepcopy(dist_manifest)
            run_manifest["created_at"] = datetime.now(timezone.utc).isoformat()
            write_manifest(run_dir / "manifest.json", run_manifest)
    finally:
        if manifest_executor is not None:
            manifest_executor.shutdown(wait=False, cancel_futures=True)
