"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_project_guide.py

Tests project guide command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import importlib
import json
import shlex
from pathlib import Path

import yaml
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.ops.variant_lifecycle import list_variant_inbox


def _default_config_path() -> Path:
    return (Path.cwd() / "config" / "workbench.yaml").resolve()


def _cvw_prefix() -> list[str]:
    if (Path.cwd() / "pyproject.toml").exists():
        return ["uv", "run", "cvw"]
    repo_root = Path(__file__).resolve().parents[2]
    return ["uv", "run", "--project", str(repo_root), "cvw"]


def _recipe_command(
    subcommand: str,
    *,
    config_path: Path | None = None,
    sot_path: Path | None = None,
) -> str:
    command = [*_cvw_prefix(), *shlex.split(subcommand)]
    if config_path is not None and config_path.resolve() != _default_config_path():
        command.extend(["--config", str(config_path.resolve())])
    if sot_path is not None:
        command.extend(["--sot-path", str(sot_path.resolve())])
    return shlex.join(command)


def _write_config(root: Path) -> Path:
    config_dir = root / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md, pdf]",
            ]
        )
        + "\n"
    )
    (variants_dir / "cover.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: cover",
                "  outputs: [md]",
                "  document_type: cover-letter",
                "  include_tags: [leadership]",
            ]
        )
        + "\n"
    )
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  projects: ../var/projects",
                "variant_lifecycle:",
                "  ttl_days: 7",
                "variants:",
                "  default: base",
            ]
        )
        + "\n"
    )
    return config_path


def _write_ranked_project_guide_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    config_dir = tmp_path / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "variant:\n  id: base\n  outputs: [md, pdf]\n"
    )
    (variants_dir / "cover.yaml").write_text(
        "variant:\n  id: cover\n  outputs: [md]\n  include_tags: [leadership]\n"
    )
    (variants_dir / "ops.yaml").write_text(
        "variant:\n  id: ops\n  outputs: [md]\n  include_tags: [reliability]\n"
    )
    (variants_dir / "blocked.yaml").write_text(
        "variant:\n  id: blocked\n  outputs: [md]\n  exclude_tags: [leadership]\n"
    )
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  projects: ../var/projects",
                "variant_lifecycle:",
                "  ttl_days: 7",
                "variants:",
                "  default: base",
            ]
        )
        + "\n"
    )
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True, exist_ok=True)
    (sot_path / "person.yaml").write_text("id: sample\nname: Sample\n")
    (sot_path / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role-1",
                "    company: Example Co",
                "    title: Engineer",
                "    start: 2021",
                "    bullets:",
                "      - id: b1",
                "        text: Led reliable delivery.",
                "        tags: [leadership, reliability]",
            ]
        )
        + "\n"
    )
    (sot_path / "projects.yaml").write_text(
        "projects:\n  - id: p1\n    name: Example Project\n    summary: Summary.\n    tags: [reliability]\n"
    )
    (sot_path / "skills.yaml").write_text(
        "skills:\n  - id: s1\n    name: Skill\n    keywords: [one]\n"
    )
    (sot_path / "education.yaml").write_text(
        "education:\n  - id: e1\n    institution: Inst\n    area: Area\n    tags: [sample]\n"
    )
    (sot_path / "letters.yaml").write_text(
        "letters:\n  - id: base\n    title: Base\n    salutation: Hello\n    closing: Thanks\n    sections:\n      - id: intro\n        text: Text\n        tags: [sample]\n"
    )
    job_path = tmp_path / "job.txt"
    job_path.write_text("Reliability reliability reliability and leadership.\n")
    return config_path, sot_path, job_path


def test_project_guide_creates_project_and_recommends_variants(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    job_path = tmp_path / "job.txt"
    job_path.write_text("Leadership and reliability focus.\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "guide",
            "--job-file",
            str(job_path),
            "--sot-path",
            "sot.sample",
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "project.guide"
    assert payload["project"]["project_dir"].endswith("var/projects/job")
    assert payload["proposal"]["variant_id"] == "proposal-job"
    assert payload["recommendations"]
    assert payload["proposal_plan"]["path"].endswith("proposal-plan.json")
    assert Path(payload["proposal_plan"]["path"]).exists()


def test_project_guide_ranks_variants_with_weighted_signal_evidence(tmp_path: Path) -> None:
    config_path, sot_path, job_path = _write_ranked_project_guide_fixture(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "guide",
            "--job-file",
            str(job_path),
            "--sot-path",
            str(sot_path),
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    recommendations = payload["recommendations"]
    assert recommendations[0]["variant_id"] == "ops"
    assert recommendations[0]["score"] > recommendations[1]["score"]
    assert recommendations[0]["score_breakdown"]["job_signal"] >= 3
    assert recommendations[0]["rationale"]
    assert recommendations[-1]["variant_id"] == "blocked"
    assert recommendations[-1]["eligible"] is False
    assert payload["project"]["base_variant"] == "ops"
    assert payload["variants"]["default"] == "base"
    assert payload["proposal_plan"]["selected_variant"] == "ops"
    assert payload["proposal_plan"]["applied_variant"] == "ops"
    assert payload["proposal_plan"]["selection_mode"] == "recommended"
    assert payload["proposal_plan"]["status"] == "targeted"
    plan_path = Path(payload["proposal_plan"]["path"])
    assert plan_path.exists()
    stored_plan = json.loads(plan_path.read_text())
    assert stored_plan["selected_variant"] == "ops"
    assert stored_plan["applied_variant"] == "ops"
    project_dir = Path(payload["project"]["project_dir"])
    project_payload = yaml.safe_load((project_dir / "project.yaml").read_text())
    assert project_payload["project"]["base_variant"] == "ops"
    proposal_variant = yaml.safe_load((project_dir / "proposals" / "variant.yaml").read_text())
    assert proposal_variant["variant"]["id"] == "proposal-job"
    assert proposal_variant["variant"]["include_tags"] == ["reliability"]


def test_project_guide_explicit_variant_preserves_requested_scaffold(tmp_path: Path) -> None:
    config_path, sot_path, job_path = _write_ranked_project_guide_fixture(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "guide",
            "--job-file",
            str(job_path),
            "--variant",
            "cover",
            "--sot-path",
            str(sot_path),
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["project"]["base_variant"] == "cover"
    assert payload["variants"]["default"] == "base"
    assert payload["proposal_plan"]["selected_variant"] == "ops"
    assert payload["proposal_plan"]["applied_variant"] == "cover"
    assert payload["proposal_plan"]["selection_mode"] == "explicit"
    default_variant = next(
        item for item in payload["recommendations"] if item["variant_id"] == "base"
    )
    assert default_variant["default"] is True
    project_dir = Path(payload["project"]["project_dir"])
    project_payload = yaml.safe_load((project_dir / "project.yaml").read_text())
    assert project_payload["project"]["base_variant"] == "cover"
    proposal_variant = yaml.safe_load((project_dir / "proposals" / "variant.yaml").read_text())
    assert proposal_variant["variant"]["id"] == "proposal-job"
    assert proposal_variant["variant"]["include_tags"] == ["leadership"]


def test_project_guide_rolls_back_project_when_retargeting_fails(
    tmp_path: Path, monkeypatch
) -> None:
    config_path, sot_path, job_path = _write_ranked_project_guide_fixture(tmp_path)
    app_module = importlib.import_module("cvworkbench.cli.app")

    def _boom(*, project_dir: Path, base_variant_id: str, config_path: Path) -> None:
        raise app_module.ProjectError("retarget failed")

    monkeypatch.setattr(app_module, "retarget_project_variant", _boom)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "guide",
            "--job-file",
            str(job_path),
            "--sot-path",
            str(sot_path),
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 1
    project_dir = tmp_path / "var" / "projects" / "job"
    assert not project_dir.exists()
    assert list_variant_inbox(config_path) == []


def test_project_guide_rolls_back_project_when_retargeting_raises_value_error(
    tmp_path: Path, monkeypatch
) -> None:
    config_path, sot_path, job_path = _write_ranked_project_guide_fixture(tmp_path)
    app_module = importlib.import_module("cvworkbench.cli.app")

    def _boom(*, project_dir: Path, base_variant_id: str, config_path: Path) -> None:
        raise ValueError("retarget failed")

    monkeypatch.setattr(app_module, "retarget_project_variant", _boom)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "guide",
            "--job-file",
            str(job_path),
            "--sot-path",
            str(sot_path),
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "retarget failed" in result.output
    project_dir = tmp_path / "var" / "projects" / "job"
    assert not project_dir.exists()
    assert list_variant_inbox(config_path) == []


def test_project_guide_reports_cleanup_failure_without_leaking_exception(
    tmp_path: Path, monkeypatch
) -> None:
    config_path, sot_path, job_path = _write_ranked_project_guide_fixture(tmp_path)
    app_module = importlib.import_module("cvworkbench.cli.app")

    def _retarget_boom(*, project_dir: Path, base_variant_id: str, config_path: Path) -> None:
        raise ValueError("retarget failed")

    def _cleanup_boom(*, project_dir: Path, config_path: Path) -> None:
        raise OSError("cleanup failed")

    monkeypatch.setattr(app_module, "retarget_project_variant", _retarget_boom)
    monkeypatch.setattr(app_module, "discard_project_workspace", _cleanup_boom)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "guide",
            "--job-file",
            str(job_path),
            "--sot-path",
            str(sot_path),
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "retarget failed" in result.output
    assert "cleanup failed" in result.output


def test_project_guide_plain_output_reports_proposal_variant(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    job_path = tmp_path / "job.txt"
    job_path.write_text("Leadership and reliability focus.\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "guide",
            "--job-file",
            str(job_path),
            "--sot-path",
            "sot.sample",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.count("project_dir:") == 1
    assert result.stdout.count("base_variant:") == 1
    assert "proposal_variant: proposal-job" in result.stdout
    assert result.stdout.count("selection_mode:") == 1
    assert result.stdout.count("preview_step:") == 1


def test_project_guide_rejects_unsafe_job_url(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "guide",
            "--job-url",
            "http://127.0.0.1/jobs/role",
            "--sot-path",
            "sot.sample",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code != 0
    assert "https" in (result.stderr or "")


def test_project_new_rejects_unsafe_job_url(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "new",
            "--job-url",
            "http://127.0.0.1/jobs/role",
            "--variant",
            "base",
            "--sot-path",
            "sot.sample",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code != 0
    assert "https" in (result.stderr or "")


def test_project_show_reports_proposal_summary_and_commands(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    job_dir = project_dir / "job"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    job_dir.mkdir(parents=True, exist_ok=True)
    signals_path = job_dir / "signals.json"
    extracted_path = job_dir / "extracted.txt"
    signals_path.write_text("{\"keywords\": [\"leadership\"]}\n")
    extracted_path.write_text("Leadership role.\n")
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: job",
                "  created_at: 2026-03-10T12:00:00+00:00",
                "  base_variant: base",
                f"  sot_path: {tmp_path / 'sot.sample'}",
                "  job:",
                "    source:",
                "      type: file",
                f"      value: {tmp_path / 'job.txt'}",
                "    extracted_path: job/extracted.txt",
                "    extracted_hash: deadbeef",
                "    raw_path: null",
                "  signals:",
                "    path: job/signals.json",
                "    hash: cafebabe",
            ]
        )
        + "\n"
    )
    (proposals_dir / "variant.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: proposal-focus",
                "  outputs: [md, pdf]",
            ]
        )
        + "\n"
    )
    (proposals_dir / "patch.yaml").write_text("patch:\n  format: project-ops\n  operations: []\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "show",
            "job",
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "project.show"
    assert payload["project"]["project_id"] == "job"
    assert payload["proposal"]["variant_id"] == "proposal-focus"
    assert payload["signals"] == {"path": str(signals_path)}
    assert payload["patch"]["is_empty"] is True
    assert payload["review"]["status"] == "build_required"
    assert payload["review"]["run_id"] is None
    assert payload["review"]["review_ready"] is False
    assert payload["commands"]["preview"] == _recipe_command(
        "preview --project job",
        config_path=config_path,
    )
    assert payload["commands"]["keep"] == _recipe_command(
        "variant keep --project job --id proposal-focus",
        config_path=config_path,
    )
    assert "reviewpack" not in payload["commands"]
    assert payload["review"]["next_command"] == _recipe_command(
        "build --project job --format md,pdf,docx",
        config_path=config_path,
    )


def test_project_show_surfaces_invalid_proposal_plan_without_failing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    job_dir = project_dir / "job"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    job_dir.mkdir(parents=True, exist_ok=True)
    signals_path = job_dir / "signals.json"
    extracted_path = job_dir / "extracted.txt"
    signals_path.write_text("{\"keywords\": [\"leadership\"]}\n")
    extracted_path.write_text("Leadership role.\n")
    (job_dir / "proposal-plan.json").write_text("{not json}\n")
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: job",
                "  created_at: 2026-03-10T12:00:00+00:00",
                "  base_variant: base",
                f"  sot_path: {tmp_path / 'sot.sample'}",
                "  job:",
                "    source:",
                "      type: file",
                f"      value: {tmp_path / 'job.txt'}",
                "    extracted_path: job/extracted.txt",
                "    extracted_hash: deadbeef",
                "    raw_path: null",
                "  signals:",
                "    path: job/signals.json",
                "    hash: cafebabe",
            ]
        )
        + "\n"
    )
    (proposals_dir / "variant.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: proposal-focus",
                "  outputs: [md, pdf]",
            ]
        )
        + "\n"
    )
    (proposals_dir / "patch.yaml").write_text("patch:\n  format: project-ops\n  operations: []\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "show",
            "job",
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["project"]["project_id"] == "job"
    assert "proposal_plan" not in payload
    assert "proposal_plan_error" in payload


def test_project_show_suggests_safe_keep_id_for_legacy_base_proposal(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    job_dir = project_dir / "job"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    job_dir.mkdir(parents=True, exist_ok=True)
    signals_path = job_dir / "signals.json"
    extracted_path = job_dir / "extracted.txt"
    signals_path.write_text("{\"keywords\": [\"leadership\"]}\n")
    extracted_path.write_text("Leadership role.\n")
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: job",
                "  created_at: 2026-03-10T12:00:00+00:00",
                "  base_variant: base",
                f"  sot_path: {tmp_path / 'sot.sample'}",
                "  job:",
                "    source:",
                "      type: file",
                f"      value: {tmp_path / 'job.txt'}",
                "    extracted_path: job/extracted.txt",
                "    extracted_hash: deadbeef",
                "    raw_path: null",
                "  signals:",
                "    path: job/signals.json",
                "    hash: cafebabe",
            ]
        )
        + "\n"
    )
    (proposals_dir / "variant.yaml").write_text("variant:\n  id: base\n  outputs: [md, pdf]\n")
    (proposals_dir / "patch.yaml").write_text("patch:\n  format: project-ops\n  operations: []\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "show",
            "job",
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["proposal"]["variant_id"] == "base"
    assert payload["commands"]["keep"] == _recipe_command(
        "variant keep --project job --id proposal-job",
        config_path=config_path,
    )


def test_project_show_reports_project_ops_patch_metadata(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    job_dir = project_dir / "job"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    job_dir.mkdir(parents=True, exist_ok=True)
    signals_path = job_dir / "signals.json"
    extracted_path = job_dir / "extracted.txt"
    signals_path.write_text("{\"keywords\": [\"leadership\"]}\n")
    extracted_path.write_text("Leadership role.\n")
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: job",
                "  created_at: 2026-03-10T12:00:00+00:00",
                "  base_variant: base",
                f"  sot_path: {tmp_path / 'sot.sample'}",
                "  job:",
                "    source:",
                "      type: file",
                f"      value: {tmp_path / 'job.txt'}",
                "    extracted_path: job/extracted.txt",
                "    extracted_hash: deadbeef",
                "    raw_path: null",
                "  signals:",
                "    path: job/signals.json",
                "    hash: cafebabe",
            ]
        )
        + "\n"
    )
    (proposals_dir / "variant.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: proposal-focus",
                "  outputs: [md, pdf]",
            ]
        )
        + "\n"
    )
    (proposals_dir / "patch.yaml").write_text(
        "\n".join(
            [
                "patch:",
                "  format: project-ops",
                "  operations:",
                "    - op: replace-experience-bullet",
                "      role_id: role",
                "      bullet_id: b1",
                "      old_text: Did work",
                "      new_text: Delivered measurable outcomes",
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "show",
            "job",
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["patch"]["format"] == "project-ops"
    assert payload["patch"]["is_empty"] is False
    assert payload["patch"]["line_count"] == 1
    assert payload["patch"]["status"] == "1 op"


def test_project_patch_replace_experience_bullet_appends_validated_op(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True, exist_ok=True)
    (sot_path / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role-1",
                "    company: Co",
                "    title: Title",
                "    start: 2020",
                "    bullets:",
                "      - id: bullet-1",
                "        text: Built platform foundations.",
                "        tags: [core]",
            ]
        )
        + "\n"
    )
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: job",
                "  created_at: 2026-03-10T12:00:00+00:00",
                "  base_variant: base",
                f"  sot_path: {sot_path}",
            ]
        )
        + "\n"
    )
    (proposals_dir / "variant.yaml").write_text("variant:\n  id: proposal-job\n  outputs: [md]\n")
    (proposals_dir / "patch.yaml").write_text(
        "patch:\n  format: project-ops\n  operations: []\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "patch",
            "replace-experience-bullet",
            "job",
            "--role-id",
            "role-1",
            "--bullet-id",
            "bullet-1",
            "--new-text",
            "Built platform foundations for regulated delivery.",
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "project.patch.replace-experience-bullet"
    assert payload["patch"]["status"] == "1 op"
    assert payload["operation"]["old_text"] == "Built platform foundations."
    patch_payload = yaml.safe_load((proposals_dir / "patch.yaml").read_text())
    assert patch_payload["patch"]["operations"][0]["new_text"] == (
        "Built platform foundations for regulated delivery."
    )


def test_project_patch_replace_project_summary_appends_validated_op(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True, exist_ok=True)
    (sot_path / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role-1",
                "    company: Co",
                "    title: Title",
                "    start: 2020",
                "    bullets:",
                "      - id: bullet-1",
                "        text: Built platform foundations.",
                "        tags: [core]",
            ]
        )
        + "\n"
    )
    (sot_path / "projects.yaml").write_text(
        "\n".join(
            [
                "projects:",
                "  - id: project-1",
                "    name: Example Project",
                "    summary: Example summary.",
                "    tags: [core]",
            ]
        )
        + "\n"
    )
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: job",
                "  created_at: 2026-03-10T12:00:00+00:00",
                "  base_variant: base",
                f"  sot_path: {sot_path}",
            ]
        )
        + "\n"
    )
    (proposals_dir / "variant.yaml").write_text("variant:\n  id: proposal-job\n  outputs: [md]\n")
    (proposals_dir / "patch.yaml").write_text(
        "patch:\n  format: project-ops\n  operations: []\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "patch",
            "replace-project-summary",
            "job",
            "--project-id",
            "project-1",
            "--new-text",
            "Example summary tailored for regulated delivery.",
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "project.patch.replace-project-summary"
    assert payload["patch"]["status"] == "1 op"
    assert payload["operation"]["old_text"] == "Example summary."
    patch_payload = yaml.safe_load((proposals_dir / "patch.yaml").read_text())
    assert patch_payload["patch"]["operations"][0]["new_text"] == (
        "Example summary tailored for regulated delivery."
    )


def test_project_patch_followup_commands_include_override_sot_path(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    recorded_sot_path = tmp_path / "local" / "sot"
    override_sot_path = tmp_path / "override" / "sot"
    recorded_sot_path.mkdir(parents=True, exist_ok=True)
    override_sot_path.mkdir(parents=True, exist_ok=True)
    for root, summary in (
        (recorded_sot_path, "Recorded summary."),
        (override_sot_path, "Override summary."),
    ):
        (root / "experience.yaml").write_text(
            "\n".join(
                [
                    "roles:",
                    "  - id: role-1",
                    "    company: Co",
                    "    title: Title",
                    "    start: 2020",
                    "    bullets:",
                    "      - id: bullet-1",
                    "        text: Built platform foundations.",
                    "        tags: [core]",
                ]
            )
            + "\n"
        )
        (root / "projects.yaml").write_text(
            "\n".join(
                [
                    "projects:",
                    "  - id: project-1",
                    "    name: Example Project",
                    f"    summary: {summary}",
                    "    tags: [core]",
                ]
            )
            + "\n"
        )
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: job",
                "  created_at: 2026-03-10T12:00:00+00:00",
                "  base_variant: base",
                f"  sot_path: {recorded_sot_path}",
            ]
        )
        + "\n"
    )
    (proposals_dir / "variant.yaml").write_text("variant:\n  id: proposal-job\n  outputs: [md]\n")
    (proposals_dir / "patch.yaml").write_text(
        "patch:\n  format: project-ops\n  operations: []\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "patch",
            "replace-project-summary",
            "job",
            "--project-id",
            "project-1",
            "--new-text",
            "Override summary tailored for regulated delivery.",
            "--sot-path",
            str(override_sot_path),
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["project"]["sot_path"] == str(override_sot_path.resolve())
    assert payload["commands"]["preview"] == _recipe_command(
        "preview --project job",
        config_path=config_path,
        sot_path=override_sot_path,
    )
    assert payload["commands"]["apply"] == _recipe_command(
        "project apply job",
        config_path=config_path,
        sot_path=override_sot_path,
    )


def test_project_patch_replace_experience_bullet_rejects_legacy_patch_format(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "local" / "sot"
    sot_path.mkdir(parents=True, exist_ok=True)
    (sot_path / "experience.yaml").write_text(
        "\n".join(
            [
                "roles:",
                "  - id: role-1",
                "    company: Co",
                "    title: Title",
                "    start: 2020",
                "    bullets:",
                "      - id: bullet-1",
                "        text: Built platform foundations.",
                "        tags: [core]",
            ]
        )
        + "\n"
    )
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: job",
                "  created_at: 2026-03-10T12:00:00+00:00",
                "  base_variant: base",
                f"  sot_path: {sot_path}",
            ]
        )
        + "\n"
    )
    (proposals_dir / "variant.yaml").write_text("variant:\n  id: proposal-job\n  outputs: [md]\n")
    (proposals_dir / "patch.yaml").write_text("patch:\n  format: unified-diff\n  diff: \"\"\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "patch",
            "replace-experience-bullet",
            "job",
            "--role-id",
            "role-1",
            "--bullet-id",
            "bullet-1",
            "--new-text",
            "Built platform foundations for regulated delivery.",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code != 0
    assert "requires format=project-ops" in (result.stderr or "")


def test_project_show_reports_pinned_reviewpack_when_latest_project_run_is_ready(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    job_dir = project_dir / "job"
    run_dir = tmp_path / "var" / "runs" / "projects" / "job" / "2026-03-10T13-00-00Z"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    job_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "signals.json").write_text("{\"keywords\": [\"leadership\"]}\n")
    (job_dir / "extracted.txt").write_text("Leadership role.\n")
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: job",
                "  created_at: 2026-03-10T12:00:00+00:00",
                "  base_variant: base",
                f"  sot_path: {tmp_path / 'sot.sample'}",
                "  job:",
                "    source:",
                "      type: file",
                f"      value: {tmp_path / 'job.txt'}",
                "    extracted_path: job/extracted.txt",
                "    extracted_hash: deadbeef",
                "    raw_path: null",
                "  signals:",
                "    path: job/signals.json",
                "    hash: cafebabe",
            ]
        )
        + "\n"
    )
    (proposals_dir / "variant.yaml").write_text("variant:\n  id: base\n  outputs: [md, pdf, docx]\n")
    (proposals_dir / "patch.yaml").write_text("patch:\n  format: project-ops\n  operations: []\n")
    (run_dir / "cv.docx").write_bytes(b"docx")
    (run_dir / "cv.pdf").write_bytes(b"pdf")
    (run_dir / "selection.json").write_text("{\"items\": []}\n")
    (run_dir / "canonical.md").write_text("base\n")
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-03-10T13:00:00+00:00",
                "formats": ["md", "pdf", "docx"],
                "outputs": {"md": "cv.md", "pdf": "cv.pdf", "docx": "cv.docx"},
                "variant": {"id": "base"},
            }
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "show",
            "job",
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["review"]["status"] == "ready"
    assert payload["review"]["run_id"] == "projects/job/2026-03-10T13-00-00Z"
    assert payload["review"]["review_ready"] is True
    assert payload["commands"]["reviewpack"] == _recipe_command(
        "reviewpack --project job --run projects/job/2026-03-10T13-00-00Z",
        config_path=config_path,
    )


def test_project_show_requires_review_artifact_files_for_ready_status(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    job_dir = project_dir / "job"
    run_dir = tmp_path / "var" / "runs" / "projects" / "job" / "2026-03-10T13-00-00Z"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    job_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "signals.json").write_text("{\"keywords\": [\"leadership\"]}\n")
    (job_dir / "extracted.txt").write_text("Leadership role.\n")
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: job",
                "  created_at: 2026-03-10T12:00:00+00:00",
                "  base_variant: base",
                f"  sot_path: {tmp_path / 'sot.sample'}",
                "  job:",
                "    source:",
                "      type: file",
                f"      value: {tmp_path / 'job.txt'}",
                "    extracted_path: job/extracted.txt",
                "    extracted_hash: deadbeef",
                "    raw_path: null",
                "  signals:",
                "    path: job/signals.json",
                "    hash: cafebabe",
            ]
        )
        + "\n"
    )
    (proposals_dir / "variant.yaml").write_text("variant:\n  id: base\n  outputs: [md, pdf, docx]\n")
    (proposals_dir / "patch.yaml").write_text("patch:\n  format: project-ops\n  operations: []\n")
    (run_dir / "selection.json").write_text("{\"items\": []}\n")
    (run_dir / "canonical.md").write_text("base\n")
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-03-10T13:00:00+00:00",
                "formats": ["md", "pdf", "docx"],
                "outputs": {"md": "cv.md", "pdf": "cv.pdf", "docx": "cv.docx"},
                "variant": {"id": "base"},
            }
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "show",
            "job",
            "--config",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["review"]["status"] == "build_required"
    assert payload["review"]["run_id"] == "projects/job/2026-03-10T13-00-00Z"
    assert payload["review"]["review_ready"] is False
    assert payload["review"]["next_command"] == _recipe_command(
        "build --project job --format md,pdf,docx",
        config_path=config_path,
    )


def test_project_new_rejects_open_with_json(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "sot.sample"
    sot_path.mkdir(parents=True, exist_ok=True)
    job_path = tmp_path / "job.txt"
    job_path.write_text("Leadership role.\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "new",
            "--job-file",
            str(job_path),
            "--sot-path",
            str(sot_path),
            "--config",
            str(config_path),
            "--open",
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "cannot be combined" in (result.stderr or "")
    assert not (tmp_path / "var" / "projects" / "job").exists()


def test_project_new_plain_prints_single_summary(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "sot.sample"
    sot_path.mkdir(parents=True, exist_ok=True)
    job_path = tmp_path / "job.txt"
    job_path.write_text("Leadership role.\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "new",
            "--job-file",
            str(job_path),
            "--sot-path",
            str(sot_path),
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.count("project_dir:") == 1
    assert "proposal_variant: proposal-job" in result.stdout
    assert result.stdout.count("preview_step:") == 1
