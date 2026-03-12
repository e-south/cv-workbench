#!/usr/bin/env python3
"""
Run a deterministic ergonomics smoke check for cv-workbench.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
ITERATIONS = 3
RUN_ID_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z")
ISO_DATETIME_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\+\d{2}:\d{2}|Z)"
)
REPO_CVW_PREFIX = ["uv", "run", "--project", str(REPO_ROOT), "cvw"]


class VerifyError(RuntimeError):
    pass


@dataclass(frozen=True)
class StepResult:
    name: str
    command: list[str]
    cwd: Path
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


def _run_step(
    name: str,
    cwd: Path,
    args: list[str],
    *,
    expected_returncode: int = 0,
    env: dict[str, str] | None = None,
) -> StepResult:
    command = [PYTHON, "-m", "cvworkbench.cli", *args]
    started_at = time.perf_counter()
    result = subprocess.run(
        command,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        text=True,
        capture_output=True,
        check=False,
    )
    duration_seconds = time.perf_counter() - started_at
    if result.returncode != expected_returncode:
        raise VerifyError(
            f"{name} failed with exit code {result.returncode}\n"
            f"command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return StepResult(
        name=name,
        command=command,
        cwd=cwd,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        duration_seconds=duration_seconds,
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def _recipe_by_id(recipes: list[dict[str, Any]], recipe_id: str) -> dict[str, Any]:
    for recipe in recipes:
        if recipe.get("id") == recipe_id:
            return recipe
    raise VerifyError(f"Recipe not found: {recipe_id}")


def _normalize_text(text: str, workspace: Path) -> str:
    aliases = {str(workspace), str(workspace.resolve())}
    for alias in list(aliases):
        if alias.startswith("/private/"):
            aliases.add(alias.removeprefix("/private"))
        elif alias.startswith("/var/"):
            aliases.add("/private" + alias)
    normalized = text
    for alias in sorted(aliases, key=len, reverse=True):
        normalized = normalized.replace(alias, "<workspace>")
    normalized = RUN_ID_PATTERN.sub("<run-id>", normalized)
    return ISO_DATETIME_PATTERN.sub("<iso-datetime>", normalized)


def _normalized_sha256(text: str, workspace: Path) -> str:
    return hashlib.sha256(_normalize_text(text, workspace).encode("utf-8")).hexdigest()


def _summary_value(stdout: str, key: str) -> str:
    prefix = f"{key}: "
    for line in stdout.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    raise VerifyError(f"Summary value not found: {key}")


def _metric_summary(values: list[float]) -> dict[str, float]:
    milliseconds = [round(value * 1000, 2) for value in values]
    return {
        "min_ms": min(milliseconds),
        "median_ms": round(statistics.median(milliseconds), 2),
        "max_ms": max(milliseconds),
    }


def _signature_diff_message(
    baseline: dict[str, dict[str, str]],
    current: dict[str, dict[str, str]],
) -> str:
    differences: list[str] = []
    for step_name in sorted(set(baseline) | set(current)):
        baseline_step = baseline.get(step_name)
        current_step = current.get(step_name)
        if baseline_step == current_step:
            continue
        if baseline_step is None:
            differences.append(f"{step_name}=missing-in-baseline")
            continue
        if current_step is None:
            differences.append(f"{step_name}=missing-in-current")
            continue
        fields = [
            field
            for field in sorted(set(baseline_step) | set(current_step))
            if baseline_step.get(field) != current_step.get(field)
        ]
        differences.append(f"{step_name}=" + ",".join(fields))
    return "; ".join(differences)


def _repo_cvw_command(subcommand: str) -> str:
    return shlex.join([*REPO_CVW_PREFIX, *shlex.split(subcommand)])


def _write_test_workspace(root: Path, *, sot_mode: str) -> Path:
    config_dir = root / "config" / "variants"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "base.yaml").write_text("variant:\n  id: base\n  outputs: [md]\n")

    config_lines = [
        "paths:",
        "  runs: ../var/runs",
        "  projects: ../var/projects",
        "  reviews: ../var/reviews",
    ]
    if sot_mode == "missing_local":
        config_lines.append("  sot: ../local/sot")
    elif sot_mode != "missing":
        config_lines.append("  sot: ../sot.sample")
    config_lines.extend(
        [
            "variants:",
            "  default: base",
            "variant_lifecycle:",
            "  ttl_days: 7",
        ]
    )
    config_path = root / "config" / "workbench.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("\n".join(config_lines) + "\n")

    if sot_mode in {"ready", "invalid"}:
        sot_root = root / "sot.sample"
        sot_root.mkdir(parents=True, exist_ok=True)
        (sot_root / "person.yaml").write_text("id: sample\nname: Sample\n")
        if sot_mode == "ready":
            (sot_root / "experience.yaml").write_text(
                "roles:\n"
                "  - id: role\n"
                "    company: Co\n"
                "    title: Title\n"
                "    start: 2020\n"
                "    bullets:\n"
                "      - id: b1\n"
                "        text: Did work\n"
                "        tags: [core]\n"
            )
            (sot_root / "projects.yaml").write_text(
                "projects:\n  - id: p1\n    name: Project\n    summary: Summary\n    tags: [core]\n"
            )
            (sot_root / "skills.yaml").write_text(
                "skills:\n  - id: s1\n    name: Skill\n    keywords: [one]\n"
            )
            (sot_root / "education.yaml").write_text(
                "education:\n  - id: e1\n    institution: Inst\n    area: Area\n    tags: [core]\n"
            )
            (sot_root / "letters.yaml").write_text(
                "letters:\n"
                "  - id: base\n"
                "    title: Base\n"
                "    salutation: Hello\n"
                "    closing: Thanks\n"
                "    sections:\n"
                "      - id: intro\n"
                "        text: Text\n"
                "        tags: [core]\n"
            )
        else:
            (sot_root / "experience.yaml").write_text("roles: not-a-list\n")
            (sot_root / "projects.yaml").write_text("projects: []\n")
            (sot_root / "skills.yaml").write_text("skills: []\n")
            (sot_root / "education.yaml").write_text("education: []\n")
            (sot_root / "letters.yaml").write_text("letters: []\n")

    return config_path


def _require_recipe_steps_include_config(
    recipe: dict[str, Any],
    config_path: Path,
    *,
    step_indexes: list[int],
) -> None:
    for index in step_indexes:
        command = recipe["steps"][index]["command"]
        argv = shlex.split(command)
        try:
            actual = Path(argv[argv.index("--config") + 1]).resolve()
        except (ValueError, IndexError):
            raise VerifyError(
                f"{recipe['id']} step {index + 1} must preserve nondefault --config"
            ) from None
        _require(
            actual == config_path.resolve(),
            f"{recipe['id']} step {index + 1} must preserve nondefault --config",
        )


def _require_recipe_steps_include_sot(
    recipe: dict[str, Any],
    sot_path: Path,
    *,
    step_indexes: list[int],
) -> None:
    for index in step_indexes:
        command = recipe["steps"][index]["command"]
        argv = shlex.split(command)
        try:
            actual = Path(argv[argv.index("--sot-path") + 1]).resolve()
        except (ValueError, IndexError):
            raise VerifyError(
                f"{recipe['id']} step {index + 1} must preserve explicit --sot-path"
            ) from None
        _require(
            actual == sot_path.resolve(),
            f"{recipe['id']} step {index + 1} must preserve explicit --sot-path",
        )


def _require_recipe_steps_exclude_sot(
    recipe: dict[str, Any],
    *,
    step_indexes: list[int],
) -> None:
    for index in step_indexes:
        command = recipe["steps"][index]["command"]
        _require(
            "--sot-path" not in command,
            f"{recipe['id']} step {index + 1} must not emit unsupported --sot-path",
        )


def _require_recipe_steps_include_workspace(
    recipe: dict[str, Any],
    workspace_root: Path,
    *,
    step_indexes: list[int],
) -> None:
    for index in step_indexes:
        command = recipe["steps"][index]["command"]
        argv = shlex.split(command)
        try:
            actual = Path(argv[argv.index("--workspace") + 1]).resolve()
        except (ValueError, IndexError):
            raise VerifyError(
                f"{recipe['id']} step {index + 1} must preserve explicit --workspace"
            ) from None
        _require(
            actual == workspace_root.resolve(),
            f"{recipe['id']} step {index + 1} must preserve explicit --workspace",
        )


def _require_recipe_step_contract(
    step: dict[str, Any],
    *,
    kind: str,
    runnable: bool,
    placeholders: list[str],
    message: str,
) -> None:
    _require(step["kind"] == kind, f"{message}: unexpected step kind")
    _require(step["runnable"] is runnable, f"{message}: unexpected runnable flag")
    _require(step["placeholders"] == placeholders, f"{message}: unexpected placeholders")


def _run_recipe_command(
    name: str,
    cwd: Path,
    command: str,
    *,
    expected_returncode: int = 0,
) -> StepResult:
    argv = shlex.split(command)
    started_at = time.perf_counter()
    result = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    duration_seconds = time.perf_counter() - started_at
    if result.returncode != expected_returncode:
        raise VerifyError(
            f"{name} failed with exit code {result.returncode}\n"
            f"command: {command}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return StepResult(
        name=name,
        command=argv,
        cwd=cwd,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        duration_seconds=duration_seconds,
    )


def main() -> int:
    if not (REPO_ROOT / "pyproject.toml").exists():
        raise VerifyError(f"Repo root not found: {REPO_ROOT}")
    if shutil.which("pandoc") is None:
        raise VerifyError("pandoc is required for preview --once ergonomics verification")

    artifacts_dir = REPO_ROOT / "var" / "verify" / "ergonomics"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    history_dir = artifacts_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    iteration_summaries: list[dict[str, Any]] = []
    step_durations: dict[str, list[float]] = {
        "init": [],
        "context": [],
        "context_compact": [],
        "workflow_recommended": [],
        "workflow_compact": [],
        "recipe_status_literal": [],
        "context_external_config": [],
        "context_external_full": [],
        "context_external_explicit": [],
        "recipe_status_explicit": [],
        "context_compact_plain_rejected": [],
        "context_missing": [],
        "workflow_missing_repair": [],
        "context_invalid": [],
        "workflow_invalid_repair": [],
        "workflow": [],
        "status": [],
        "build": [],
        "context_after_md_build": [],
        "context_after_review_ready_build": [],
        "preview_once": [],
        "preview_reject_nonlocal_host": [],
        "project_guide": [],
        "project_show": [],
        "project_show_after_build": [],
        "variant_inbox": [],
        "project_build": [],
        "variant_review_ready_build": [],
        "project_preview_once": [],
        "project_reviewpack": [],
        "project_reviewpack_force": [],
        "project_import": [],
    }
    full_context_lines_all: list[int] = []
    compact_context_lines_all: list[int] = []
    baseline_signatures: dict[str, dict[str, str]] | None = None

    for iteration in range(1, ITERATIONS + 1):
        with tempfile.TemporaryDirectory(prefix="cvw-ergonomics-") as tmpdir_str:
            workspace = Path(tmpdir_str).resolve()
            steps: list[StepResult] = []

            steps.append(_run_step("init", workspace, ["init", "--sample-default", "--plain"]))
            (workspace / "var" / "runs" / "bad-run").mkdir(parents=True, exist_ok=True)
            (workspace / "var" / "projects" / "bad-project").mkdir(parents=True, exist_ok=True)

            context_step = _run_step("context", workspace, ["context", "--json"])
            steps.append(context_step)
            context_payload = json.loads(context_step.stdout)
            configured_sot = Path(context_payload["sot"]["configured_path"]).resolve()
            _require(context_payload["command"] == "context", "Unexpected context command payload")
            _require(
                context_payload["sot"]["status"] == "ready",
                "Expected sample workspace SoT to be ready",
            )
            _require(
                configured_sot == (workspace / "sot.sample").resolve(),
                "Configured SoT path did not resolve to workspace-local sot.sample",
            )

            compact_context_step = _run_step(
                "context_compact",
                workspace,
                ["context", "--json", "--compact"],
            )
            steps.append(compact_context_step)
            compact_context_payload = json.loads(compact_context_step.stdout)
            full_context_lines = len(context_step.stdout.splitlines())
            compact_context_lines = len(compact_context_step.stdout.splitlines())
            _require(
                compact_context_lines < full_context_lines,
                "context --json --compact must be smaller than the full context payload",
            )
            _require(
                compact_context_payload["recommended_workflows"][0]["id"] == "automation.verify",
                "Compact context must recommend automation.verify first in a ready sample workspace",
            )
            _require(
                compact_context_payload["recommended_workflows"][0]["command"]
                == _repo_cvw_command("workflow --id automation.verify"),
                "Compact context must include the exact workflow follow-up command",
            )
            _require(
                compact_context_payload["recommended_workflows"][0]["json_command"]
                == _repo_cvw_command("workflow --id automation.verify --json --compact"),
                "Compact context must include the exact machine-readable workflow follow-up command",
            )
            _require(
                "latest_by_variant" not in compact_context_payload["runs"],
                "Compact context must collapse detailed run inventories into summaries",
            )
            _require(
                compact_context_payload["runs"]["invalid_summary"] == "bad-run",
                "Compact context must surface invalid run directories without failing",
            )
            _require(
                compact_context_payload["projects"]["invalid_summary"] == "bad-project",
                "Compact context must surface invalid project directories without failing",
            )

            workflow_recommended_step = _run_recipe_command(
                "workflow_recommended",
                workspace,
                compact_context_payload["recommended_workflows"][0]["command"],
            )
            steps.append(workflow_recommended_step)
            workflow_recommended_output = (
                workflow_recommended_step.stdout + workflow_recommended_step.stderr
            )
            _require(
                "automation.verify" in workflow_recommended_output,
                "Recommended workflow command must be replayable from the workspace",
            )

            workflow_compact_step = _run_recipe_command(
                "workflow_compact",
                workspace,
                compact_context_payload["recommended_workflows"][0]["json_command"],
            )
            steps.append(workflow_compact_step)
            workflow_compact_payload = json.loads(workflow_compact_step.stdout)
            _require(
                workflow_compact_payload["sot"]["status"] == "ready",
                "Compact workflow JSON must preserve SoT readiness state",
            )
            _require(
                "files" not in workflow_compact_payload["sot"],
                "Compact workflow JSON must omit full SoT file inventories",
            )
            _require(
                len(workflow_compact_step.stdout.splitlines()) < full_context_lines,
                "Compact workflow JSON must stay smaller than the full context payload",
            )

            external_context_step = _run_step(
                "context_external_config",
                REPO_ROOT,
                [
                    "context",
                    "--json",
                    "--compact",
                    "--config",
                    str(workspace / "config" / "workbench.yaml"),
                ],
            )
            steps.append(external_context_step)
            external_context_payload = json.loads(external_context_step.stdout)
            _require(
                str(workspace / "config" / "workbench.yaml")
                in external_context_payload["recommended_workflows"][0]["command"],
                "Compact context must preserve nondefault --config in follow-up workflow commands",
            )
            _require(
                str(workspace / "config" / "workbench.yaml")
                in external_context_payload["recommended_workflows"][0]["json_command"],
                "Compact context must preserve nondefault --config in machine-readable follow-up commands",
            )

            external_context_full_step = _run_step(
                "context_external_full",
                REPO_ROOT,
                [
                    "context",
                    "--json",
                    "--config",
                    str(workspace / "config" / "workbench.yaml"),
                ],
            )
            steps.append(external_context_full_step)
            external_context_full_payload = json.loads(external_context_full_step.stdout)
            external_recipes = external_context_full_payload["recipes"]
            _require_recipe_steps_include_config(
                _recipe_by_id(external_recipes, "review.import"),
                workspace / "config" / "workbench.yaml",
                step_indexes=[0, 2],
            )
            _require_recipe_steps_include_config(
                _recipe_by_id(external_recipes, "project.guide"),
                workspace / "config" / "workbench.yaml",
                step_indexes=[0, 1, 2, 3],
            )
            _require_recipe_steps_include_config(
                _recipe_by_id(external_recipes, "project.inspect"),
                workspace / "config" / "workbench.yaml",
                step_indexes=[0, 1],
            )
            _require_recipe_steps_include_config(
                _recipe_by_id(external_recipes, "variant.manage"),
                workspace / "config" / "workbench.yaml",
                step_indexes=[0, 1, 2],
            )

            explicit_context_step = _run_step(
                "context_external_explicit",
                REPO_ROOT,
                [
                    "context",
                    "--json",
                    "--config",
                    str(workspace / "config" / "workbench.yaml"),
                    "--sot-path",
                    str(workspace / "sot.sample"),
                ],
            )
            steps.append(explicit_context_step)
            explicit_context_payload = json.loads(explicit_context_step.stdout)
            explicit_recipes = explicit_context_payload["recipes"]
            explicit_automation = _recipe_by_id(explicit_recipes, "automation.verify")
            explicit_baseline = _recipe_by_id(explicit_recipes, "baseline.build_preview")
            explicit_review = _recipe_by_id(explicit_recipes, "review.import")
            explicit_project = _recipe_by_id(explicit_recipes, "project.guide")
            explicit_refresh = _recipe_by_id(explicit_recipes, "context.refresh")

            for recipe in [explicit_automation, explicit_baseline]:
                _require_recipe_steps_include_config(
                    recipe,
                    workspace / "config" / "workbench.yaml",
                    step_indexes=[0, 1, 2],
                )
                _require_recipe_steps_include_sot(
                    recipe,
                    workspace / "sot.sample",
                    step_indexes=[0, 1, 2],
                )
            _require_recipe_steps_include_config(
                explicit_project,
                workspace / "config" / "workbench.yaml",
                step_indexes=[0, 1, 2, 3],
            )
            _require_recipe_steps_include_sot(
                explicit_project,
                workspace / "sot.sample",
                step_indexes=[0, 2, 3],
            )
            _require_recipe_steps_exclude_sot(explicit_project, step_indexes=[1])
            _require_recipe_steps_include_config(
                explicit_review,
                workspace / "config" / "workbench.yaml",
                step_indexes=[0, 2],
            )
            _require_recipe_steps_exclude_sot(explicit_review, step_indexes=[0, 2, 3])
            _require_recipe_steps_include_config(
                explicit_refresh,
                workspace / "config" / "workbench.yaml",
                step_indexes=[0],
            )
            _require_recipe_steps_include_sot(
                explicit_refresh,
                workspace / "sot.sample",
                step_indexes=[0],
            )

            recipe_status_step = _run_recipe_command(
                "recipe_status_explicit",
                REPO_ROOT,
                explicit_automation["steps"][0]["command"],
            )
            steps.append(recipe_status_step)
            recipe_status_output = recipe_status_step.stdout + recipe_status_step.stderr
            _require(
                str(workspace / "sot.sample") in recipe_status_output,
                "Replayed recipe status step must inspect the explicit SoT path",
            )

            compact_plain_step = _run_step(
                "context_compact_plain_rejected",
                workspace,
                ["context", "--compact", "--plain"],
                expected_returncode=2,
            )
            steps.append(compact_plain_step)
            _require(
                "--compact requires --json" in compact_plain_step.stderr,
                "context --compact --plain must fail fast with an explicit error",
            )

            recipes = context_payload["recipes"]
            automation_recipe = _recipe_by_id(recipes, "automation.verify")
            _require(
                automation_recipe["steps"][0]["command"] == _repo_cvw_command("status"),
                "automation.verify must start with the status command",
            )
            review_recipe = _recipe_by_id(recipes, "review.import")
            variant_manage_recipe = _recipe_by_id(recipes, "variant.manage")
            review_steps = [step["command"] for step in review_recipe["steps"]]
            _require(
                any("import-docx --from " in command for command in review_steps),
                "review.import recipe must use import-docx --from",
            )
            _require(
                "variant keep --project" in variant_manage_recipe["steps"][1]["command"]
                and "<project-id>" in variant_manage_recipe["steps"][1]["command"]
                and "--id" in variant_manage_recipe["steps"][1]["command"]
                and "<variant-id>" in variant_manage_recipe["steps"][1]["command"],
                "variant.manage must teach selector-first keep commands for project proposals",
            )
            _require(
                "variant discard --project" in variant_manage_recipe["steps"][2]["command"]
                and "<project-id>" in variant_manage_recipe["steps"][2]["command"]
                and "--yes" in variant_manage_recipe["steps"][2]["command"],
                "variant.manage must teach selector-first discard commands for project proposals",
            )
            _require_recipe_step_contract(
                automation_recipe["steps"][0],
                kind="command",
                runnable=True,
                placeholders=[],
                message="automation.verify status step",
            )
            _require_recipe_step_contract(
                review_recipe["steps"][1],
                kind="manual",
                runnable=False,
                placeholders=["<variant>"],
                message="review.import edit step",
            )
            _require_recipe_step_contract(
                review_recipe["steps"][3],
                kind="manual",
                runnable=False,
                placeholders=[],
                message="review.import notes step",
            )
            review_diff_stop = review_recipe["stop_conditions"][2]
            _require(
                "review_diff_only" in review_diff_stop
                and "author a real SoT patch manually" in review_diff_stop,
                "review.import recipe must make review_diff_only handling explicit",
            )
            _require(
                context_payload["runs"]["invalid_summary"] == "bad-run",
                "Full context must surface invalid run directories without failing",
            )
            _require(
                context_payload["projects"]["invalid_summary"] == "bad-project",
                "Full context must surface invalid project directories without failing",
            )

            recipe_status_literal = _run_recipe_command(
                "recipe_status_literal",
                workspace,
                automation_recipe["steps"][0]["command"],
            )
            steps.append(recipe_status_literal)
            recipe_status_literal_output = (
                recipe_status_literal.stdout + recipe_status_literal.stderr
            )
            _require(
                str(workspace / "sot.sample") in recipe_status_literal_output,
                "Literal automation status step must be replayable from the workspace",
            )

            workflow_step = _run_step(
                "workflow",
                workspace,
                ["workflow", "--json", "--id", "automation.verify"],
            )
            steps.append(workflow_step)
            workflow_payload = json.loads(workflow_step.stdout)
            _require(
                [recipe["id"] for recipe in workflow_payload["recipes"]] == ["automation.verify"],
                "workflow --id automation.verify did not isolate the automation recipe",
            )
            _require(
                "files" in workflow_payload["sot"],
                "Full workflow JSON must retain full SoT details when compact mode is not requested",
            )

            status_step = _run_step("status", workspace, ["status", "--json"])
            steps.append(status_step)
            status_payload = json.loads(status_step.stdout)
            _require(
                status_payload["sot"]["path"] == str(workspace / "sot.sample"),
                "status must report the configured sample SoT path",
            )
            _require(
                status_payload["variants"]["config_count"] >= 1,
                "status must report configured variants",
            )
            _require(
                status_payload["runs"]["invalid_summary"] == "bad-run",
                "status must report invalid run directories without failing",
            )
            _require(
                status_payload["projects"]["invalid_summary"] == "bad-project",
                "status must report invalid project directories without failing",
            )

            missing_config = _write_test_workspace(
                workspace / "cases" / "missing-local",
                sot_mode="missing_local",
            )
            missing_context_step = _run_step(
                "context_missing",
                REPO_ROOT,
                ["context", "--json", "--compact", "--config", str(missing_config)],
            )
            steps.append(missing_context_step)
            missing_context_payload = json.loads(missing_context_step.stdout)
            _require(
                missing_context_payload["recommended_workflows"][0]["id"]
                == "bootstrap.local_workspace",
                "Missing local scaffold must recommend bootstrap.local_workspace first",
            )

            missing_workflow_step = _run_step(
                "workflow_missing_repair",
                REPO_ROOT,
                [
                    "workflow",
                    "--json",
                    "--id",
                    "bootstrap.local_workspace",
                    "--config",
                    str(missing_config),
                ],
            )
            steps.append(missing_workflow_step)
            missing_workflow_payload = json.loads(missing_workflow_step.stdout)
            _require(
                missing_workflow_payload["recipes"][0]["steps"][0]["command"].startswith(
                    "uv run cvw init"
                ),
                "bootstrap.local_workspace must begin with a valid init command",
            )
            _require_recipe_steps_include_workspace(
                missing_workflow_payload["recipes"][0],
                workspace / "cases" / "missing-local",
                step_indexes=[0],
            )
            _require_recipe_steps_include_config(
                missing_workflow_payload["recipes"][0],
                missing_config,
                step_indexes=[1, 2],
            )

            invalid_config = _write_test_workspace(
                workspace / "cases" / "invalid", sot_mode="invalid"
            )
            invalid_context_step = _run_step(
                "context_invalid",
                REPO_ROOT,
                ["context", "--json", "--compact", "--config", str(invalid_config)],
            )
            steps.append(invalid_context_step)
            invalid_context_payload = json.loads(invalid_context_step.stdout)
            _require(
                invalid_context_payload["recommended_workflows"][0]["id"] == "repair.sot_yaml",
                "Invalid SoT must recommend repair.sot_yaml first",
            )

            invalid_workflow_step = _run_step(
                "workflow_invalid_repair",
                REPO_ROOT,
                ["workflow", "--json", "--id", "repair.sot_yaml", "--config", str(invalid_config)],
            )
            steps.append(invalid_workflow_step)
            invalid_workflow_payload = json.loads(invalid_workflow_step.stdout)
            _require_recipe_steps_include_config(
                invalid_workflow_payload["recipes"][0],
                invalid_config,
                step_indexes=[0, 2, 3],
            )

            build_step = _run_step(
                "build",
                workspace,
                ["build", "--variant", "base", "--format", "md", "--plain"],
            )
            steps.append(build_step)
            _require(
                (workspace / "var" / "dist" / "base" / "cv.md").exists(),
                "Markdown build output missing",
            )

            context_after_md_build_step = _run_step(
                "context_after_md_build",
                workspace,
                ["context", "--json", "--compact"],
            )
            steps.append(context_after_md_build_step)
            context_after_md_build_payload = json.loads(context_after_md_build_step.stdout)
            _require(
                "review.import"
                not in [
                    item["id"] for item in context_after_md_build_payload["recommended_workflows"]
                ],
                "Compact context must not recommend review.import when the latest run is not review-ready",
            )

            preview_step = _run_step(
                "preview_once",
                workspace,
                ["preview", "--variant", "base", "--once", "--plain"],
            )
            steps.append(preview_step)
            preview_lines = preview_step.stdout.splitlines()
            _require(
                any(line.startswith("preview_file:") for line in preview_lines),
                "preview --once must report preview_file",
            )
            _require(
                not any(line.startswith("preview_url:") for line in preview_lines),
                "preview --once must not report preview_url",
            )
            _require(
                (workspace / "var" / "dist" / "base" / "cv.html").exists(),
                "HTML preview output missing",
            )

            job_path = workspace / "job.txt"
            job_path.write_text("Leadership, reliability, and automation focus.\n")
            project_guide_step = _run_step(
                "project_guide",
                workspace,
                ["project", "guide", "--job-file", str(job_path), "--json"],
            )
            steps.append(project_guide_step)
            project_guide_payload = json.loads(project_guide_step.stdout)
            project_id = project_guide_payload["project"]["project_id"]
            proposal_variant_id = project_guide_payload["proposal"]["variant_id"]

            project_show_step = _run_step(
                "project_show",
                workspace,
                ["project", "show", project_id, "--json"],
            )
            steps.append(project_show_step)
            project_show_payload = json.loads(project_show_step.stdout)
            _require(
                project_show_payload["proposal"]["variant_id"] == proposal_variant_id,
                "project show must expose the proposal variant id",
            )
            _require(
                project_show_payload["commands"]["preview"]
                == _repo_cvw_command(f"preview --project {project_id}"),
                "project show must emit a replayable preview command",
            )
            _require(
                project_show_payload["commands"]["keep"]
                == _repo_cvw_command(
                    f"variant keep --project {project_id} --id {proposal_variant_id}"
                ),
                "project show must emit a ready-to-run keep command",
            )

            variant_inbox_step = _run_step(
                "variant_inbox",
                workspace,
                ["variant", "inbox", "--json"],
            )
            steps.append(variant_inbox_step)
            variant_inbox_payload = json.loads(variant_inbox_step.stdout)
            project_entry = next(
                entry
                for entry in variant_inbox_payload["entries"]
                if entry.get("project_id") == project_id
            )
            _require(
                project_entry["selector_kind"] == "project",
                "variant.inbox must expose project selector metadata for project proposals",
            )
            _require(
                f"variant keep --project {project_id}" in project_entry["keep_command"],
                "variant.inbox must emit a ready-to-run keep command for project proposals",
            )
            _require(
                f"preview --project {project_id}" in project_entry["preview_command"],
                "variant.inbox must emit a ready-to-run preview command for project proposals",
            )

            project_build_step = _run_step(
                "project_build",
                workspace,
                ["build", "--project", project_id, "--format", "md,pdf,docx", "--plain"],
            )
            steps.append(project_build_step)

            project_show_after_build_step = _run_step(
                "project_show_after_build",
                workspace,
                ["project", "show", project_id, "--json"],
            )
            steps.append(project_show_after_build_step)
            project_show_after_build_payload = json.loads(project_show_after_build_step.stdout)
            review_run_id = project_show_after_build_payload["review"]["run_id"]
            _require(
                project_show_after_build_payload["review"]["status"] == "ready",
                "project show must report review.status=ready after a review-ready project build",
            )
            _require(
                project_show_after_build_payload["commands"]["reviewpack"]
                == _repo_cvw_command(f"reviewpack --project {project_id} --run {review_run_id}"),
                "project show must emit a pinned reviewpack command when the latest project run is review-ready",
            )

            variant_review_ready_build_step = _run_step(
                "variant_review_ready_build",
                workspace,
                ["build", "--variant", "base", "--format", "md,pdf,docx", "--plain"],
            )
            steps.append(variant_review_ready_build_step)

            context_after_review_ready_build_step = _run_step(
                "context_after_review_ready_build",
                workspace,
                ["context", "--json", "--compact"],
            )
            steps.append(context_after_review_ready_build_step)
            context_after_review_ready_payload = json.loads(
                context_after_review_ready_build_step.stdout
            )
            _require(
                "review.import"
                in [
                    item["id"]
                    for item in context_after_review_ready_payload["recommended_workflows"]
                ],
                "Compact context must recommend review.import after a review-ready run exists",
            )

            project_preview_step = _run_step(
                "project_preview_once",
                workspace,
                [
                    "preview",
                    "--project",
                    project_id,
                    "--sot-path",
                    str(workspace / "sot.sample"),
                    "--once",
                    "--plain",
                ],
            )
            steps.append(project_preview_step)
            _require(
                (workspace / "var" / "dist" / "base" / "cv.html").exists(),
                "Project preview --once must produce HTML output",
            )

            preview_reject_nonlocal_host_step = _run_step(
                "preview_reject_nonlocal_host",
                workspace,
                ["preview", "--variant", "base", "--plain"],
                expected_returncode=2,
                env={"CVW_DEV_HOST": "0.0.0.0"},
            )
            steps.append(preview_reject_nonlocal_host_step)
            _require(
                "non-local preview binding is not supported"
                in preview_reject_nonlocal_host_step.stderr,
                "preview must fail fast on non-local host bindings",
            )

            project_run_dir = Path(_summary_value(project_build_step.stdout, "run_dir"))
            _require(
                (project_run_dir / "cv.docx").exists(),
                "Project build must persist DOCX output under the run directory",
            )
            _require(
                (project_run_dir / "cv.pdf").exists(),
                "Project build must persist PDF output under the run directory",
            )
            _require(
                (project_run_dir / "selection.json").exists(),
                "Project build must persist selection metadata under the run directory",
            )
            project_reviewpack_step = _run_step(
                "project_reviewpack",
                workspace,
                ["reviewpack", "--run", str(project_run_dir), "--plain"],
            )
            steps.append(project_reviewpack_step)
            expected_project_run = f"projects/{project_id}/"
            _require(
                f"run_id: {expected_project_run}" in project_reviewpack_step.stdout,
                "reviewpack must package the explicit project-scoped run",
            )
            _require(
                f"out_dir: {workspace / 'var' / 'reviews' / 'projects' / project_id}"
                in project_reviewpack_step.stdout,
                "reviewpack --run must isolate project review packs under var/reviews/projects/<project-id>",
            )

            project_reviewpack_force_step = _run_step(
                "project_reviewpack_force",
                workspace,
                ["reviewpack", "--run", str(project_run_dir), "--force", "--plain"],
            )
            steps.append(project_reviewpack_force_step)
            _require(
                f"run_id: {expected_project_run}" in project_reviewpack_force_step.stdout,
                "reviewpack --force must refresh the same deterministic project-scoped run",
            )

            project_import_step = _run_step(
                "project_import",
                workspace,
                [
                    "import-docx",
                    "--from",
                    f"var/reviews/projects/{project_id}/cv.docx",
                    "--project",
                    project_id,
                    "--plain",
                ],
            )
            steps.append(project_import_step)
            _require(
                f"run_id: {expected_project_run}" in project_import_step.stdout,
                "import-docx must resolve the latest project-scoped run for the project",
            )

            signatures = {
                step.name: {
                    "stdout_sha256": _normalized_sha256(step.stdout, workspace),
                    "stderr_sha256": _normalized_sha256(step.stderr, workspace),
                }
                for step in steps
            }
            if baseline_signatures is None:
                baseline_signatures = signatures
            else:
                diff_message = _signature_diff_message(baseline_signatures, signatures)
                _require(
                    signatures == baseline_signatures,
                    "Ergonomics verify produced non-repeatable normalized outputs across runs"
                    + (f": {diff_message}" if diff_message else ""),
                )

            full_context_lines_all.append(full_context_lines)
            compact_context_lines_all.append(compact_context_lines)
            for step in steps:
                step_durations[step.name].append(step.duration_seconds)

            iteration_summaries.append(
                {
                    "iteration": iteration,
                    "workspace": str(workspace),
                    "metrics": {
                        "context_json_lines": full_context_lines,
                        "context_compact_json_lines": compact_context_lines,
                    },
                    "adversarial_cases": {
                        "missing_recommendation": missing_context_payload["recommended_workflows"][
                            0
                        ]["id"],
                        "invalid_recommendation": invalid_context_payload["recommended_workflows"][
                            0
                        ]["id"],
                        "invalid_runs_summary": context_payload["runs"]["invalid_summary"],
                        "invalid_projects_summary": context_payload["projects"]["invalid_summary"],
                        "project_review_run_id_prefix": f"projects/{project_id}/",
                    },
                    "signatures": signatures,
                    "steps": [
                        {
                            "name": step.name,
                            "cwd": str(step.cwd),
                            "command": " ".join(step.command),
                            "returncode": step.returncode,
                            "duration_ms": round(step.duration_seconds * 1000, 2),
                            "stdout": step.stdout,
                            "stderr": step.stderr,
                        }
                        for step in steps
                    ],
                }
            )

    summary = {
        "iterations": ITERATIONS,
        "metrics": {
            "context_json_lines": full_context_lines_all,
            "context_compact_json_lines": compact_context_lines_all,
            "context_json_lines_median": statistics.median(full_context_lines_all),
            "context_compact_json_lines_median": statistics.median(compact_context_lines_all),
            "step_durations_ms": {
                name: _metric_summary(values) for name, values in step_durations.items()
            },
        },
        "iterations_detail": iteration_summaries,
        "status": "ok",
    }
    summary_path = artifacts_dir / "latest.json"
    history_path = history_dir / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-ergonomics.json"
    )
    summary_text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    summary_path.write_text(summary_text)
    history_path.write_text(summary_text)
    print(
        json.dumps(
            {"status": "ok", "summary_path": str(summary_path), "history_path": str(history_path)},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerifyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
