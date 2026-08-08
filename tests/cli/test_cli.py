"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_cli.py

Tests the CLI surface and validation behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app
from tests.utils import strip_ansi


def test_cli_help_lists_commands() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "validate" in output
    assert "init" in output
    assert "quickstart" in output
    assert "doctor" in output
    assert "bootstrap" in output
    assert "workflow" in output
    assert "build" in output
    assert "render" in output
    assert "dev" in output
    assert "clean" in output
    assert "tailor" in output
    assert "diff" in output
    assert "sync" in output
    assert "explain" in output
    assert "reviewpack" in output
    assert "import-docx" in output
    assert "job" in output
    assert "theme" in output
    assert "variant" in output
    assert "tags" in output
    assert "sot" in output


def test_validate_succeeds_with_sample_sot() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["validate", "--sot-path", "sot.sample"])

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "status:" in output
    assert "sot_path:" in output


def test_validate_fails_on_missing_required_file(tmp_path: Path) -> None:
    (tmp_path / "person.yaml").write_text("id: sample\nname: Sample\n")

    runner = CliRunner()

    result = runner.invoke(app, ["validate", "--sot-path", str(tmp_path)])

    assert result.exit_code != 0
    assert "experience.yaml" in result.stderr


def test_tailor_prints_draft_paths(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    variants_dir = config_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    (variants_dir / "base.yaml").write_text(
        "\n".join(
            [
                "variant:",
                "  id: base",
                "  outputs: [md]",
            ]
        )
        + "\n"
    )
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                "  drafts: ../var/drafts",
                "variant_lifecycle:",
                "  ttl_days: 7",
                "variants:",
                "  default: base",
            ]
        )
        + "\n"
    )
    job_path = tmp_path / "job.md"
    job_path.write_text("Role: Test\nNeeds: Python\n")
    draft_dir = tmp_path / "var" / "drafts" / "sample-role"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "tailor",
            "--job",
            str(job_path),
            "--out",
            str(draft_dir),
            "--base-variant",
            "base",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "draft_dir:" in output
    assert "variant:" in output
    assert "patch:" in output


def test_apply_prints_status(tmp_path: Path) -> None:
    draft_dir = tmp_path / "draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / "patch.diff").write_text("")
    sot_dir = tmp_path / "sot"
    sot_dir.mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "apply",
            "--draft",
            str(draft_dir),
            "--sot-path",
            str(sot_dir),
        ],
    )

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "status:" in output
    assert "no_changes" in output
    assert "reason:" in output
    assert "empty_patch" in output


def test_build_prints_output_locations() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["build", "--variant", "base", "--format", "md", "--sot-path", "sot.sample"],
    )

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "output_md:" in output
    assert "cv.md" in output
    assert "run_dir:" in output


def test_build_reports_unsupported_format_without_traceback() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "build",
            "--variant",
            "base",
            "--format",
            "xyz",
            "--sot-path",
            "sot.sample",
            "--plain",
        ],
    )

    assert result.exit_code != 0
    assert "Unsupported output format 'xyz'" in (result.stderr or "")
    assert "Traceback" not in (result.stderr or "")


def test_parse_formats_dedupes_preserving_first_seen_order() -> None:
    app_module = importlib.import_module("cvworkbench.cli.app")

    assert app_module._parse_formats(["md,pdf", "md", " docx , pdf "]) == [
        "md",
        "pdf",
        "docx",
    ]
    assert app_module._parse_formats(["   "]) == []


def test_build_rejects_whitespace_only_format_argument(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
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
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "variants:",
                "  default: base",
                "render:",
                f"  themes_dir: {Path('build/themes').resolve()}",
                "  theme: default",
                "  style_preset: modern",
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "build",
            "--variant",
            "base",
            "--format",
            "   ",
            "--sot-path",
            "sot.sample",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code != 0
    assert "No output formats selected" in (result.stderr or "")


def test_render_rejects_whitespace_only_format_argument(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
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
    config_path = config_dir / "workbench.yaml"
    config_path.write_text(
        "\n".join(
            [
                "variants:",
                "  default: base",
                "render:",
                f"  themes_dir: {Path('build/themes').resolve()}",
                "  theme: default",
                "  style_preset: modern",
            ]
        )
        + "\n"
    )
    canonical = tmp_path / "canonical.md"
    canonical.write_text("# Example\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "render",
            "--canonical",
            str(canonical),
            "--variant",
            "base",
            "--format",
            "   ",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code != 0
    assert "No output formats selected" in (result.stderr or "")


def test_cli_module_entrypoint() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "cvworkbench.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Usage" in result.stdout


def test_doctor_reports_missing_config(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["doctor", "--plain", "--config", str(tmp_path / "missing.yaml")],
    )

    assert result.exit_code != 0
    assert "Config file not found" in result.stderr


def test_job_add_reports_missing_config(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "job",
            "add",
            "--plain",
            "--url",
            "https://example.com/context",
            "--config",
            str(tmp_path / "missing.yaml"),
        ],
    )

    assert result.exit_code != 0
    assert "Config file not found" in result.stderr


def test_reviewpack_help_mentions_required_artifacts() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["reviewpack", "--help"])

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "existing run" in output
    assert "cv.docx" in output
    assert "selection.json" in output
    assert "--run" in output
    assert "--project" in output
    assert "--force" in output


def test_import_docx_help_mentions_run_resolution() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["import-docx", "--help"])

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "--from" in output
    assert "canonical.md" in output
    assert "patch.yaml using structured project-ops" in output
    assert "--run" in output
    assert "--variant" in output
    assert "--project" in output


def test_theme_list_ships_multiple_themes() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["theme", "list", "--plain"])

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "default" in output
    assert "editorial" in output
    assert "signal" in output


def test_theme_info_reports_presets() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["theme", "info", "default", "--plain"])

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "presets:" in output
    assert "modern" in output
    assert "compact" in output


def test_variant_keep_and_discard_help_expose_project_selector() -> None:
    runner = CliRunner()

    keep_result = runner.invoke(app, ["variant", "keep", "--help"])
    discard_result = runner.invoke(app, ["variant", "discard", "--help"])

    assert keep_result.exit_code == 0
    assert discard_result.exit_code == 0
    assert "--project" in strip_ansi(keep_result.stdout)
    assert "--project" in strip_ansi(discard_result.stdout)


def test_build_and_preview_help_expose_selector_constraints() -> None:
    runner = CliRunner()

    build_result = runner.invoke(app, ["build", "--help"])
    preview_result = runner.invoke(app, ["preview", "--help"])

    assert build_result.exit_code == 0
    assert preview_result.exit_code == 0
    build_output = " ".join(strip_ansi(build_result.stdout).split())
    preview_output = " ".join(strip_ansi(preview_result.stdout).split())
    assert "cannot be combined with --project" in build_output
    assert "cannot be combined with --variant" in build_output
    assert "cannot be combined with --project" in preview_output
    assert "cannot be combined with --variant" in preview_output
    assert "non-local bind addresses are not supported" in preview_output


def test_project_help_lists_show_command() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["project", "--help"])

    assert result.exit_code == 0
    assert "show" in strip_ansi(result.stdout)


def test_project_guide_help_mentions_open_json_constraint() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["project", "guide", "--help"])

    assert result.exit_code == 0
    assert "--open" in strip_ansi(result.stdout)
    assert "--json" in strip_ansi(result.stdout)
    assert "cannot be combined" in strip_ansi(result.stdout)


def test_project_new_help_mentions_open_json_constraint() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["project", "new", "--help"])

    assert result.exit_code == 0
    assert "--open" in strip_ansi(result.stdout)
    assert "--json" in strip_ansi(result.stdout)
    assert "cannot be combined" in strip_ansi(result.stdout)


def test_help_surfaces_descriptions_for_discovery_commands() -> None:
    runner = CliRunner()

    top_level = runner.invoke(app, ["--help"], terminal_width=160)
    variant_help = runner.invoke(app, ["variant", "--help"], terminal_width=160)
    workflow_help = runner.invoke(app, ["workflow", "--help"], terminal_width=160)

    assert top_level.exit_code == 0
    assert variant_help.exit_code == 0
    assert workflow_help.exit_code == 0
    top_level_output = " ".join(strip_ansi(top_level.stdout).replace("│", " ").split())
    variant_output = " ".join(strip_ansi(variant_help.stdout).replace("│", " ").split())
    workflow_output = " ".join(strip_ansi(workflow_help.stdout).replace("│", " ").split())
    assert "Inspect configured variants and manage ephemeral draft/project" in top_level_output
    assert "Create, inspect, and apply job-tailoring project workspaces." in top_level_output
    assert "Show configured variants alongside lifecycle inbox entries." in variant_output
    assert "List pending draft/project proposals and flag entries that are" in variant_output
    assert "expired pending garbage collection." in variant_output
    assert "Use --json --compact when you want recipe-focused retrieval" in workflow_output


def test_variant_keep_resolves_project_variant_path(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config" / "variants"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config" / "workbench.yaml"
    config_path.write_text("paths:\n  projects: ../var/projects\n")
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    variant_path = proposals_dir / "variant.yaml"
    variant_path.write_text("variant:\n  id: base\n  outputs: [md]\n")
    (proposals_dir / "patch.yaml").write_text("patch:\n  format: project-ops\n  operations: []\n")
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: job",
                "  base_variant: base",
                f"  sot_path: {tmp_path / 'sot.sample'}",
            ]
        )
        + "\n"
    )

    captured: dict[str, object] = {}
    app_module = importlib.import_module("cvworkbench.cli.app")

    def _fake_keep_variant(*, variant_path: Path, config_path: Path, variant_id, label):
        captured["variant_path"] = variant_path
        captured["config_path"] = config_path
        return type(
            "_KeepResult",
            (),
            {"variant_id": variant_id or "base", "variant_path": variant_path, "status": "kept"},
        )()

    monkeypatch.setattr(app_module, "keep_variant", _fake_keep_variant)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "variant",
            "keep",
            "--project",
            "job",
            "--id",
            "base-keep",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 0
    assert captured["variant_path"] == variant_path
    assert captured["config_path"] == config_path


def test_variant_discard_resolves_project_variant_path(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config" / "workbench.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("paths:\n  projects: ../var/projects\n")
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    variant_path = proposals_dir / "variant.yaml"
    variant_path.write_text("variant:\n  id: base\n  outputs: [md]\n")
    (proposals_dir / "patch.yaml").write_text("patch:\n  format: project-ops\n  operations: []\n")
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: job",
                "  base_variant: base",
                f"  sot_path: {tmp_path / 'sot.sample'}",
            ]
        )
        + "\n"
    )

    captured: dict[str, object] = {}
    app_module = importlib.import_module("cvworkbench.cli.app")

    def _fake_discard_variant(*, variant_path: Path, config_path: Path, confirm: bool):
        captured["variant_path"] = variant_path
        captured["config_path"] = config_path
        return type("_DiscardResult", (), {"variant_path": variant_path, "status": "dry_run"})()

    monkeypatch.setattr(app_module, "discard_variant", _fake_discard_variant)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "variant",
            "discard",
            "--project",
            "job",
            "--config",
            str(config_path),
            "--plain",
        ],
    )

    assert result.exit_code == 2
    assert captured["variant_path"] == variant_path
    assert captured["config_path"] == config_path


def test_variant_inbox_json_exposes_project_selector_commands(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config" / "workbench.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("paths:\n  projects: ../var/projects\n")
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    variant_path = proposals_dir / "variant.yaml"
    patch_path = proposals_dir / "patch.yaml"
    variant_path.write_text("variant:\n  id: base\n  outputs: [md]\n")
    patch_path.write_text("patch:\n  format: project-ops\n  operations: []\n")

    entry = type(
        "_Entry",
        (),
        {
            "variant_id": "base",
            "variant_path": variant_path,
            "cleanup_path": proposals_dir,
            "source": "project",
            "status": "ephemeral",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "label": "job",
        },
    )()
    app_module = importlib.import_module("cvworkbench.cli.app")
    monkeypatch.setattr(app_module, "list_variant_inbox", lambda _config: [entry])

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["variant", "inbox", "--json", "--config", str(config_path)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    inbox_entry = payload["entries"][0]
    assert inbox_entry["selector_kind"] == "project"
    assert inbox_entry["project_id"] == "job"
    assert inbox_entry["status"] == "ephemeral"
    assert inbox_entry["registry_status"] == "ephemeral"
    assert inbox_entry["expired"] is False
    assert inbox_entry["patch_path"] == str(patch_path)
    assert "variant keep --project job --id proposal-job" in inbox_entry["keep_command"]
    assert "variant discard --project job --yes" in inbox_entry["discard_command"]
    assert "preview --project job" in inbox_entry["preview_command"]


def test_variant_inbox_json_flags_expired_entries_and_gc_hint(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config" / "workbench.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("paths:\n  projects: ../var/projects\n")
    project_dir = tmp_path / "var" / "projects" / "job"
    proposals_dir = project_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    variant_path = proposals_dir / "variant.yaml"
    patch_path = proposals_dir / "patch.yaml"
    variant_path.write_text("variant:\n  id: base\n  outputs: [md]\n")
    patch_path.write_text("patch:\n  format: project-ops\n  operations: []\n")

    entry = type(
        "_Entry",
        (),
        {
            "variant_id": "base",
            "variant_path": variant_path,
            "cleanup_path": proposals_dir,
            "source": "project",
            "status": "ephemeral",
            "expires_at": "2026-02-07T00:00:00+00:00",
            "label": "job",
        },
    )()
    app_module = importlib.import_module("cvworkbench.cli.app")
    monkeypatch.setattr(app_module, "list_variant_inbox", lambda _config: [entry])

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["variant", "inbox", "--json", "--config", str(config_path)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    inbox_entry = payload["entries"][0]
    assert inbox_entry["status"] == "expired_pending_gc"
    assert inbox_entry["registry_status"] == "ephemeral"
    assert inbox_entry["expired"] is True
    assert "variant gc" in payload["gc_command"]


def test_project_help_distinguishes_guide_and_new() -> None:
    runner = CliRunner()

    new_result = runner.invoke(app, ["project", "new", "--help"])
    guide_result = runner.invoke(app, ["project", "guide", "--help"])

    assert new_result.exit_code == 0
    assert guide_result.exit_code == 0
    new_output = " ".join(strip_ansi(new_result.stdout).split())
    guide_output = " ".join(strip_ansi(guide_result.stdout).split())
    assert "Create a project workspace directly" in new_output
    assert "Use `project guide`" in new_output
    assert "rank candidate variants" in guide_output
