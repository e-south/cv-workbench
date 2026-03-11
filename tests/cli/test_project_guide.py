"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_project_guide.py

Tests project guide command behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app


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
    assert payload["recommendations"]


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
    (proposals_dir / "patch.yaml").write_text("patch:\n  format: unified-diff\n  diff: \"\"\n")

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
    (proposals_dir / "patch.yaml").write_text("patch:\n  format: unified-diff\n  diff: \"\"\n")
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
    assert result.stdout.count("preview_step:") == 1
