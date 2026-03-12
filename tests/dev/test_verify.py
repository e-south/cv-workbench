"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/dev/test_verify.py

Tests the repo-local verify harness contract.

Module Author(s): Codex
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

import cvworkbench.dev.verify as verify_module
from cvworkbench.dev.verify import CommandExecution, VerifyStep, VerifyWorkspace

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_prepare_verify_workspace_bootstraps_isolated_contract(tmp_path: Path) -> None:
    workspace = verify_module.prepare_verify_workspace(REPO_ROOT, tmp_path / "verify")

    assert workspace.root == (tmp_path / "verify").resolve()
    assert workspace.config_path.exists()
    assert workspace.job_file.exists()
    assert (workspace.config_path.parent / "variants" / "base.yaml").exists()

    config = yaml.safe_load(workspace.config_path.read_text())
    assert config["paths"]["sot"] == str((REPO_ROOT / "sot.sample").resolve())
    assert config["render"]["themes_dir"] == str((REPO_ROOT / "build" / "themes").resolve())
    assert config["variants"]["default"] == "base"


def test_run_verify_writes_machine_readable_summary_on_success(tmp_path: Path) -> None:
    workspace_root = tmp_path / "verify"
    summary = verify_module.run_verify(REPO_ROOT, workspace_root, runner=_success_runner)

    assert summary["status"] == "ok"
    assert summary["error"] is None
    assert len(summary["steps"]) == 7

    summary_path = Path(summary["contract"]["summary_path"])
    assert summary_path.exists()
    persisted = json.loads(summary_path.read_text())
    assert persisted["status"] == "ok"
    assert persisted["steps"][-1]["id"] == "import-docx"
    assert persisted["steps"][-1]["artifacts"]["run_id"] == "2026-01-02T00-00-00Z"


def test_run_verify_fails_fast_when_expected_artifact_is_missing(tmp_path: Path) -> None:
    workspace_root = tmp_path / "verify"
    summary = verify_module.run_verify(
        REPO_ROOT, workspace_root, runner=_missing_preview_artifact_runner
    )

    assert summary["status"] == "failed"
    assert "preview output missing" in str(summary["error"])
    assert summary["steps"][3]["id"] == "preview.once"
    assert summary["steps"][3]["status"] == "failed"


def test_run_verify_fails_preflight_when_required_binary_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    workspace_root = tmp_path / "verify"

    def fake_which(name: str) -> str | None:
        if name == "pandoc":
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr(verify_module.shutil, "which", fake_which)
    summary = verify_module.run_verify(REPO_ROOT, workspace_root, runner=_unexpected_runner)

    assert summary["status"] == "failed"
    assert summary["steps"] == []
    assert summary["error"] == "Required binary not found: pandoc"


def _success_runner(step: VerifyStep, workspace: VerifyWorkspace) -> CommandExecution:
    return _emit_success(step, workspace, preview_html=True)


def _missing_preview_artifact_runner(
    step: VerifyStep, workspace: VerifyWorkspace
) -> CommandExecution:
    return _emit_success(step, workspace, preview_html=step.id != "preview.once")


def _emit_success(
    step: VerifyStep,
    workspace: VerifyWorkspace,
    *,
    preview_html: bool,
) -> CommandExecution:
    if step.id == "doctor":
        return CommandExecution(
            0,
            json.dumps(
                {
                    "command": "doctor",
                    "data": {
                        "pandoc": "ok (pandoc 3.1.0)",
                        workspace.pdf_engine: f"ok ({workspace.pdf_engine} 1.0)",
                    },
                }
            ),
        )

    if step.id == "context":
        return CommandExecution(
            0,
            json.dumps(
                {
                    "command": "context",
                    "config": {
                        "path": str(workspace.config_path),
                        "project": {"name": "cv-workbench"},
                    },
                    "sot": {
                        "configured_path": str(workspace.sot_path),
                        "path": str(workspace.sot_path),
                        "status": "ready",
                        "errors": [],
                    },
                    "variants": {"default": "base"},
                    "recipes": [
                        {"id": "baseline.build_preview"},
                        {"id": "automation.verify"},
                        {"id": "review.import"},
                        {"id": "project.guide"},
                    ],
                }
            ),
        )

    if step.id == "build":
        dist_dir = workspace.root / "var" / "dist" / "base"
        run_dir = workspace.root / "var" / "runs" / "2026-01-02T00-00-00Z"
        dist_dir.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir(parents=True, exist_ok=True)
        files = {
            dist_dir / "cv.md": "md\n",
            dist_dir / "cv.pdf": "pdf\n",
            dist_dir / "cv.docx": "docx\n",
            dist_dir / "manifest.json": "{}\n",
            run_dir / "manifest.json": "{}\n",
            run_dir / "canonical.md": "canonical\n",
            run_dir / "resume.json": "{}\n",
        }
        for path, content in files.items():
            path.write_text(content)
        return CommandExecution(
            0,
            json.dumps(
                {
                    "command": "build",
                    "data": {
                        "variant": "base",
                        "formats": "md,pdf,docx",
                        "outputs_dir": str(dist_dir),
                        "run_dir": str(run_dir),
                        "canonical": str(run_dir / "canonical.md"),
                        "resume_json": str(run_dir / "resume.json"),
                        "manifest_dist": str(dist_dir / "manifest.json"),
                        "manifest_run": str(run_dir / "manifest.json"),
                        "output_md": str(dist_dir / "cv.md"),
                        "output_pdf": str(dist_dir / "cv.pdf"),
                        "output_docx": str(dist_dir / "cv.docx"),
                    },
                }
            ),
        )

    if step.id == "preview.once":
        html_path = workspace.root / "var" / "dist" / "base" / "cv.html"
        if preview_html:
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text("<html></html>\n")
        return CommandExecution(
            0,
            json.dumps(
                {
                    "command": "serve",
                    "data": {
                        "output_html": str(html_path),
                        "preview_file": str(html_path),
                        "watching": "false",
                        "controls": "t=theme p=preset v=variant f=format r=rebuild x=stop",
                    },
                }
            ),
        )

    if step.id == "project.guide":
        project_dir = workspace.root / "var" / "projects" / "job"
        (project_dir / "proposals").mkdir(parents=True, exist_ok=True)
        (project_dir / "project.yaml").write_text("project:\n  id: job\n")
        (project_dir / "proposals" / "variant.yaml").write_text("variant:\n  id: base\n")
        (project_dir / "proposals" / "patch.yaml").write_text(
            "patch:\n  format: project-ops\n  operations: []\n"
        )
        return CommandExecution(
            0,
            json.dumps(
                {
                    "command": "project.guide",
                    "project": {
                        "project_id": "job",
                        "project_dir": str(project_dir),
                        "base_variant": "base",
                        "job_source": str(workspace.job_file),
                    },
                    "recommendations": [{"variant_id": "base", "score": 1.0}],
                }
            ),
        )

    if step.id == "reviewpack":
        out_dir = workspace.root / "var" / "reviews" / "base"
        out_dir.mkdir(parents=True, exist_ok=True)
        for path, content in {
            out_dir / "cv.docx": "docx\n",
            out_dir / "cv.pdf": "pdf\n",
            out_dir / "review.md": "# Review\n",
        }.items():
            path.write_text(content)
        return CommandExecution(
            0,
            json.dumps(
                {
                    "command": "reviewpack",
                    "data": {
                        "out_dir": str(out_dir),
                        "docx": str(out_dir / "cv.docx"),
                        "pdf": str(out_dir / "cv.pdf"),
                        "review": str(out_dir / "review.md"),
                        "run_id": "2026-01-02T00-00-00Z",
                    },
                }
            ),
        )

    if step.id == "import-docx":
        draft_dir = workspace.root / "var" / "drafts" / "import-2026-01-03T00-00-00Z"
        draft_dir.mkdir(parents=True, exist_ok=True)
        for path, content in {
            draft_dir / "patch.diff": "--- canonical.md\n+++ imported.md\n",
            draft_dir
            / "draft.json": '{"apply_status": "review_diff_only", "patch_path": "patch.diff"}\n',
            draft_dir / "notes.md": "# Notes\n",
            draft_dir / "imported.md": "after\n",
        }.items():
            path.write_text(content)
        return CommandExecution(
            0,
            json.dumps(
                {
                    "command": "import-docx",
                    "data": {
                        "draft_dir": str(draft_dir),
                        "patch": str(draft_dir / "patch.diff"),
                        "metadata": str(draft_dir / "draft.json"),
                        "notes": str(draft_dir / "notes.md"),
                        "imported_markdown": str(draft_dir / "imported.md"),
                        "run_id": "2026-01-02T00-00-00Z",
                    },
                }
            ),
        )

    raise AssertionError(f"Unexpected step: {step.id}")


def _unexpected_runner(_step: VerifyStep, _workspace: VerifyWorkspace) -> CommandExecution:
    raise AssertionError("runner should not be called when preflight fails")
