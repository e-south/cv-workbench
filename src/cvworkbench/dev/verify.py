"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/src/cvworkbench/dev/verify.py

Deterministic repo-local verify harness for canonical CLI journeys.

Module Author(s): Codex
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from cvworkbench.config import resolve_pdf_engine
from cvworkbench.inputs.validation import validate_sot


class VerifyError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifyWorkspace:
    repo_root: Path
    root: Path
    config_path: Path
    sot_path: Path
    job_file: Path
    themes_dir: Path
    evidence_dir: Path
    summary_path: Path
    pdf_engine: str


@dataclass(frozen=True)
class CommandExecution:
    exit_code: int
    stdout: str
    stderr: str = ""


Verifier = Callable[[dict[str, Any], VerifyWorkspace, dict[str, Any]], dict[str, str]]
CommandRunner = Callable[["VerifyStep", VerifyWorkspace], CommandExecution]


@dataclass(frozen=True)
class VerifyStep:
    id: str
    title: str
    argv: tuple[str, ...]
    verify: Verifier


def prepare_verify_workspace(repo_root: Path, workspace_root: Path | None = None) -> VerifyWorkspace:
    resolved_repo_root = repo_root.resolve()
    _require(
        (resolved_repo_root / "pyproject.toml").exists(),
        f"Repo root not found or invalid: {resolved_repo_root}",
    )

    if workspace_root is None:
        resolved_workspace = Path(tempfile.mkdtemp(prefix="cvw-verify-")).resolve()
    else:
        resolved_workspace = workspace_root.resolve()
        if resolved_workspace.exists():
            _require(
                not any(resolved_workspace.iterdir()),
                f"Workspace already exists and is not empty: {resolved_workspace}",
            )
        else:
            resolved_workspace.mkdir(parents=True, exist_ok=False)

    config_dir = resolved_workspace / "config"
    variants_dir = config_dir / "variants"
    evidence_dir = resolved_workspace / "evidence"
    fixtures_dir = resolved_workspace / "fixtures"
    for path in [config_dir, variants_dir, evidence_dir, fixtures_dir]:
        path.mkdir(parents=True, exist_ok=True)

    for relative in ["var/dist", "var/runs", "var/drafts", "var/reviews", "var/projects"]:
        (resolved_workspace / relative).mkdir(parents=True, exist_ok=True)

    source_variants = resolved_repo_root / "config" / "variants"
    variant_files = sorted(source_variants.glob("*.yaml"))
    _require(variant_files, f"No variant files found: {source_variants}")
    for path in variant_files:
        shutil.copy2(path, variants_dir / path.name)

    sot_path = (resolved_repo_root / "sot.sample").resolve()
    themes_dir = (resolved_repo_root / "build" / "themes").resolve()
    pdf_engine = _resolve_pdf_engine_or_default(resolved_repo_root / "config" / "workbench.yaml")

    config_payload = {
        "project": {"name": "cv-workbench"},
        "paths": {
            "sot": str(sot_path),
            "dist": "../var/dist",
            "runs": "../var/runs",
            "drafts": "../var/drafts",
            "reviews": "../var/reviews",
            "projects": "../var/projects",
        },
        "variants": {"default": "base"},
        "variant_lifecycle": {"ttl_days": 7},
        "render": {
            "themes_dir": str(themes_dir),
            "theme": "default",
            "style_preset": "modern",
            "pdf_engine": pdf_engine,
        },
        "site": {"sync_mode": "local"},
        "registry": {"user_agent": "cv-workbench/verify"},
    }
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(yaml.safe_dump(config_payload, sort_keys=False))

    job_file = fixtures_dir / "job.txt"
    job_file.write_text(
        "\n".join(
            [
                "Leadership and reliability focus.",
                "Build deterministic workflows with explicit contracts and review discipline.",
            ]
        )
        + "\n"
    )

    return VerifyWorkspace(
        repo_root=resolved_repo_root,
        root=resolved_workspace,
        config_path=config_path,
        sot_path=sot_path,
        job_file=job_file,
        themes_dir=themes_dir,
        evidence_dir=evidence_dir,
        summary_path=resolved_workspace / "verify-summary.json",
        pdf_engine=pdf_engine,
    )


def run_verify(
    repo_root: Path,
    workspace_root: Path | None = None,
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    workspace = prepare_verify_workspace(repo_root, workspace_root)
    summary: dict[str, Any] = {
        "status": "running",
        "error": None,
        "repo_root": str(workspace.repo_root),
        "contract": {
            "entrypoint": "uv run python scripts/verify_repo.py",
            "workspace_policy": "isolated-temp-workspace",
            "failure_policy": "fail-fast-no-silent-fallback",
            "journeys": [
                "doctor",
                "context",
                "build",
                "preview.once",
                "project.guide",
                "reviewpack",
                "import-docx",
            ],
            "summary_path": str(workspace.summary_path),
        },
        "workspace": {
            "root": str(workspace.root),
            "config": str(workspace.config_path),
            "sot": str(workspace.sot_path),
            "job_file": str(workspace.job_file),
            "themes_dir": str(workspace.themes_dir),
            "evidence_dir": str(workspace.evidence_dir),
        },
        "preflight": [],
        "steps": [],
    }

    active_runner = runner or _run_subprocess
    state: dict[str, Any] = {}

    try:
        summary["preflight"] = run_preflight(workspace)
        _write_summary(summary, workspace.summary_path)

        for index, step in enumerate(_build_steps(workspace), start=1):
            stdout_path = workspace.evidence_dir / f"{index:02d}-{_slug(step.id)}.stdout.json"
            stderr_path = workspace.evidence_dir / f"{index:02d}-{_slug(step.id)}.stderr.txt"
            started = time.perf_counter()
            execution = active_runner(step, workspace)
            duration = round(time.perf_counter() - started, 3)

            stdout_path.write_text(execution.stdout)
            stderr_path.write_text(execution.stderr)

            step_result: dict[str, Any] = {
                "id": step.id,
                "title": step.title,
                "argv": list(step.argv),
                "exit_code": execution.exit_code,
                "duration_seconds": duration,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "status": "failed" if execution.exit_code != 0 else "ok",
                "artifacts": {},
                "payload": None,
                "error": None,
            }
            summary["steps"].append(step_result)

            if execution.exit_code != 0:
                stderr_preview = execution.stderr.strip() or execution.stdout.strip() or "no output"
                raise VerifyError(f"{step.id} failed: {stderr_preview}")

            payload = _load_json_output(execution.stdout, step.id)
            step_result["payload"] = payload
            step_result["artifacts"] = step.verify(payload, workspace, state)
            _write_summary(summary, workspace.summary_path)
    except VerifyError as exc:
        summary["status"] = "failed"
        summary["error"] = str(exc)
        if summary["steps"]:
            summary["steps"][-1]["status"] = "failed"
            summary["steps"][-1]["error"] = str(exc)
    else:
        summary["status"] = "ok"
    finally:
        _write_summary(summary, workspace.summary_path)

    return summary


def run_preflight(workspace: VerifyWorkspace) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    _append_check(
        checks,
        "repo_root",
        workspace.repo_root / "pyproject.toml",
        f"found {workspace.repo_root / 'pyproject.toml'}",
    )
    _append_binary_check(checks, "uv")
    _append_binary_check(checks, "pandoc")
    _append_binary_check(checks, workspace.pdf_engine)

    errors = validate_sot(workspace.sot_path)
    _require(not errors, f"Sample SoT is invalid: {'; '.join(errors)}")
    _append_check(checks, "sample_sot", workspace.sot_path, f"validated {workspace.sot_path}")
    _append_check(
        checks,
        "themes_dir",
        workspace.themes_dir,
        f"found {workspace.themes_dir}",
    )
    _append_check(
        checks,
        "variants_dir",
        workspace.config_path.parent / "variants",
        f"found {workspace.config_path.parent / 'variants'}",
    )
    _append_check(checks, "job_fixture", workspace.job_file, f"created {workspace.job_file}")

    for relative in ["var/dist", "var/runs", "var/drafts", "var/reviews", "var/projects"]:
        target = workspace.root / relative
        _require(target.exists(), f"Artifact directory missing: {target}")
        probe = target / ".verify-write-test"
        probe.write_text("ok\n")
        probe.unlink()
        checks.append(
            {
                "name": f"writable:{relative}",
                "status": "ok",
                "detail": f"writable {target}",
            }
        )

    return checks


def _build_steps(workspace: VerifyWorkspace) -> tuple[VerifyStep, ...]:
    config = str(workspace.config_path)
    sot = str(workspace.sot_path)
    job_file = str(workspace.job_file)
    review_docx = workspace.root / "var" / "reviews" / "base" / "cv.docx"
    return (
        VerifyStep(
            id="doctor",
            title="Check external toolchain readiness",
            argv=("uv", "run", "cvw", "doctor", "--json", "--config", config),
            verify=_verify_doctor,
        ),
        VerifyStep(
            id="context",
            title="Inspect workspace context",
            argv=("uv", "run", "cvw", "context", "--json", "--config", config),
            verify=_verify_context,
        ),
        VerifyStep(
            id="build",
            title="Build canonical outputs",
            argv=(
                "uv",
                "run",
                "cvw",
                "build",
                "--json",
                "--config",
                config,
                "--sot-path",
                sot,
                "--variant",
                "base",
                "--format",
                "md,pdf,docx",
            ),
            verify=_verify_build,
        ),
        VerifyStep(
            id="preview.once",
            title="Build preview once without a session",
            argv=(
                "uv",
                "run",
                "cvw",
                "preview",
                "--json",
                "--once",
                "--config",
                config,
                "--sot-path",
                sot,
                "--variant",
                "base",
            ),
            verify=_verify_preview_once,
        ),
        VerifyStep(
            id="project.guide",
            title="Create a local project guide bundle",
            argv=(
                "uv",
                "run",
                "cvw",
                "project",
                "guide",
                "--json",
                "--config",
                config,
                "--sot-path",
                sot,
                "--job-file",
                job_file,
            ),
            verify=_verify_project_guide,
        ),
        VerifyStep(
            id="reviewpack",
            title="Create a review pack from the latest run",
            argv=("uv", "run", "cvw", "reviewpack", "--json", "--variant", "base", "--config", config),
            verify=_verify_reviewpack,
        ),
        VerifyStep(
            id="import-docx",
            title="Import the review DOCX against the latest base run",
            argv=(
                "uv",
                "run",
                "cvw",
                "import-docx",
                "--json",
                "--from",
                str(review_docx),
                "--variant",
                "base",
                "--config",
                config,
            ),
            verify=_verify_import_docx,
        ),
    )


def _verify_doctor(
    payload: dict[str, Any], workspace: VerifyWorkspace, _state: dict[str, Any]
) -> dict[str, str]:
    data = _expect_summary_payload(payload, "doctor")
    required = {"pandoc", workspace.pdf_engine}
    artifacts: dict[str, str] = {}
    for name in sorted(required):
        detail = data.get(name)
        _require(detail is not None, f"doctor output missing key: {name}")
        _require(str(detail).startswith("ok"), f"doctor reported {name} as not ready: {detail}")
        artifacts[name] = str(detail)
    return artifacts


def _verify_context(
    payload: dict[str, Any], workspace: VerifyWorkspace, _state: dict[str, Any]
) -> dict[str, str]:
    _require(payload.get("command") == "context", "context output command mismatch")
    _require(payload["config"]["path"] == str(workspace.config_path), "context config path drift")
    _require(payload["sot"]["status"] == "ready", "context did not resolve sample SoT as ready")
    _require(payload["sot"]["path"] == str(workspace.sot_path), "context SoT path drift")
    recipe_ids = [recipe["id"] for recipe in payload.get("recipes", [])]
    _require(
        recipe_ids[:4]
        == ["baseline.build_preview", "automation.verify", "review.import", "project.guide"],
        f"context recipe order drift: {recipe_ids[:4]}",
    )
    return {
        "sot_status": payload["sot"]["status"],
        "default_variant": str(payload["variants"]["default"]),
        "recipes_checked": ",".join(recipe_ids[:4]),
    }


def _verify_build(
    payload: dict[str, Any], workspace: VerifyWorkspace, state: dict[str, Any]
) -> dict[str, str]:
    data = _expect_summary_payload(payload, "build")
    _require(data.get("variant") == "base", f"build variant drift: {data.get('variant')}")
    formats = str(data.get("formats", "")).split(",")
    _require(formats == ["md", "pdf", "docx"], f"build formats drift: {formats}")

    output_md = _require_path(data, "output_md")
    output_pdf = _require_path(data, "output_pdf")
    output_docx = _require_path(data, "output_docx")
    manifest_dist = _require_path(data, "manifest_dist")
    manifest_run = _require_path(data, "manifest_run")
    canonical = _require_path(data, "canonical")
    resume_json = _require_path(data, "resume_json")
    run_dir = _require_path(data, "run_dir")

    for path in [
        output_md,
        output_pdf,
        output_docx,
        manifest_dist,
        manifest_run,
        canonical,
        resume_json,
        run_dir,
    ]:
        _require(path.exists(), f"build artifact missing: {path}")

    _require(
        run_dir.parent == workspace.root / "var" / "runs",
        f"build run_dir outside isolated workspace: {run_dir}",
    )
    state["build_run_id"] = run_dir.name
    return {
        "run_dir": str(run_dir),
        "run_id": run_dir.name,
        "output_md": str(output_md),
        "output_pdf": str(output_pdf),
        "output_docx": str(output_docx),
    }


def _verify_preview_once(
    payload: dict[str, Any], workspace: VerifyWorkspace, _state: dict[str, Any]
) -> dict[str, str]:
    data = _expect_summary_payload(payload, "serve")
    html_path = _require_path(data, "output_html")
    _require(html_path.exists(), f"preview output missing: {html_path}")
    preview_path = data.get("preview_file") or data.get("preview_url")
    _require(preview_path == str(html_path), "preview --once should return the local HTML path")
    _require(data.get("watching") == "false", f"preview --once watching drift: {data.get('watching')}")
    session_path = workspace.root / "var" / "runs" / "preview" / "session.json"
    _require(not session_path.exists(), f"preview --once wrote a session file: {session_path}")
    return {
        "output_html": str(html_path),
        "preview_file": str(preview_path),
        "session_path": str(session_path),
    }


def _verify_project_guide(
    payload: dict[str, Any], workspace: VerifyWorkspace, state: dict[str, Any]
) -> dict[str, str]:
    _require(payload.get("command") == "project.guide", "project guide output command mismatch")
    project_dir = Path(payload["project"]["project_dir"])
    project_file = project_dir / "project.yaml"
    variant_path = project_dir / "proposals" / "variant.yaml"
    patch_path = project_dir / "proposals" / "patch.yaml"
    for path in [project_dir, project_file, variant_path, patch_path]:
        _require(path.exists(), f"project guide artifact missing: {path}")
    _require(
        project_dir.parent == workspace.root / "var" / "projects",
        f"project guide wrote outside isolated workspace: {project_dir}",
    )
    recommendations = payload.get("recommendations", [])
    _require(bool(recommendations), "project guide returned no recommendations")
    state["project_id"] = str(payload["project"]["project_id"])
    return {
        "project_id": str(payload["project"]["project_id"]),
        "project_dir": str(project_dir),
        "recommendations": str(len(recommendations)),
    }


def _verify_reviewpack(
    payload: dict[str, Any], workspace: VerifyWorkspace, state: dict[str, Any]
) -> dict[str, str]:
    data = _expect_summary_payload(payload, "reviewpack")
    out_dir = _require_path(data, "out_dir")
    docx_path = _require_path(data, "docx")
    pdf_path = _require_path(data, "pdf")
    review_path = _require_path(data, "review")
    for path in [out_dir, docx_path, pdf_path, review_path]:
        _require(path.exists(), f"reviewpack artifact missing: {path}")
    _require(
        out_dir.parent == workspace.root / "var" / "reviews",
        f"reviewpack wrote outside isolated workspace: {out_dir}",
    )
    expected_run_id = state.get("build_run_id")
    _require(expected_run_id is not None, "build_run_id missing before reviewpack verification")
    _require(
        data.get("run_id") == expected_run_id,
        f"reviewpack resolved unexpected run_id: {data.get('run_id')} != {expected_run_id}",
    )
    return {
        "out_dir": str(out_dir),
        "run_id": str(data["run_id"]),
    }


def _verify_import_docx(
    payload: dict[str, Any], workspace: VerifyWorkspace, state: dict[str, Any]
) -> dict[str, str]:
    data = _expect_summary_payload(payload, "import-docx")
    draft_dir = _require_path(data, "draft_dir")
    patch_path = _require_path(data, "patch")
    metadata_path = _require_path(data, "metadata")
    notes_path = _require_path(data, "notes")
    imported_path = _require_path(data, "imported_markdown")
    for path in [draft_dir, patch_path, metadata_path, notes_path, imported_path]:
        _require(path.exists(), f"import-docx artifact missing: {path}")
    _require(
        draft_dir.parent == workspace.root / "var" / "drafts",
        f"import-docx wrote outside isolated workspace: {draft_dir}",
    )
    expected_run_id = state.get("build_run_id")
    _require(expected_run_id is not None, "build_run_id missing before import-docx verification")
    _require(
        data.get("run_id") == expected_run_id,
        f"import-docx resolved unexpected run_id: {data.get('run_id')} != {expected_run_id}",
    )
    return {
        "draft_dir": str(draft_dir),
        "patch": str(patch_path),
        "metadata": str(metadata_path),
        "run_id": str(data["run_id"]),
    }


def _run_subprocess(step: VerifyStep, workspace: VerifyWorkspace) -> CommandExecution:
    result = subprocess.run(
        step.argv,
        cwd=workspace.repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandExecution(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _load_json_output(stdout: str, step_id: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise VerifyError(f"{step_id} did not produce valid JSON output") from exc
    if not isinstance(payload, dict):
        raise VerifyError(f"{step_id} produced a non-object JSON payload")
    return payload


def _expect_summary_payload(payload: dict[str, Any], command: str) -> dict[str, str]:
    _require(payload.get("command") == command, f"summary command drift: expected {command}")
    data = payload.get("data")
    _require(isinstance(data, dict), f"{command} summary payload missing data object")
    return {str(key): str(value) for key, value in data.items()}


def _require_path(data: dict[str, str], key: str) -> Path:
    value = data.get(key)
    _require(value is not None and value.strip(), f"summary payload missing path key: {key}")
    return Path(value)


def _append_check(
    checks: list[dict[str, str]],
    name: str,
    path: Path,
    detail: str,
) -> None:
    _require(path.exists(), f"Required path not found: {path}")
    checks.append({"name": name, "status": "ok", "detail": detail})


def _append_binary_check(checks: list[dict[str, str]], name: str) -> None:
    resolved = shutil.which(name)
    _require(resolved is not None, f"Required binary not found: {name}")
    checks.append({"name": f"binary:{name}", "status": "ok", "detail": resolved})


def _resolve_pdf_engine_or_default(config_path: Path) -> str:
    try:
        return resolve_pdf_engine(config_path) or "xelatex"
    except (FileNotFoundError, ValueError):
        return "xelatex"


def _slug(value: str) -> str:
    return value.replace(".", "-")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def _write_summary(summary: dict[str, Any], summary_path: Path) -> None:
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
