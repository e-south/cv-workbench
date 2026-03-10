"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_workflow.py

Tests workflow command output.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app
from tests.utils import strip_ansi


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


def _workflow_command(
    recipe_id: str,
    *,
    config_path: Path | None = None,
    sot_path: Path | None = None,
    json_output: bool = False,
    compact: bool = False,
) -> str:
    command = [*_cvw_prefix(), "workflow", "--id", recipe_id]
    if json_output:
        command.append("--json")
    if compact:
        command.append("--compact")
    if config_path is not None and config_path.resolve() != _default_config_path():
        command.extend(["--config", str(config_path.resolve())])
    if sot_path is not None:
        command.extend(["--sot-path", str(sot_path.resolve())])
    return shlex.join(command)


def _init_command(*, sample_default: bool, workspace_root: Path) -> str:
    command = [*_cvw_prefix(), "init"]
    if sample_default:
        command.append("--sample-default")
    if workspace_root.resolve() != Path.cwd().resolve():
        command.extend(["--workspace", str(workspace_root.resolve())])
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
                "  sot: ../sot.sample",
                "  runs: ../var/runs",
                "  projects: ../var/projects",
                "  reviews: ../var/reviews",
                "variants:",
                "  default: base",
                "variant_lifecycle:",
                "  ttl_days: 7",
            ]
        )
        + "\n"
    )
    return config_path


def _write_minimal_sot(root: Path) -> Path:
    sot_sample = root / "sot.sample"
    sot_sample.mkdir(parents=True, exist_ok=True)
    (sot_sample / "person.yaml").write_text("id: sample\nname: Sample\n")
    (sot_sample / "experience.yaml").write_text(
        "roles:\n  - id: role\n    company: Co\n    title: Title\n    start: 2020\n    bullets:\n      - id: b1\n        text: Did work\n        tags: [core]\n"
    )
    (sot_sample / "projects.yaml").write_text(
        "projects:\n  - id: p1\n    name: Project\n    summary: Summary\n    tags: [core]\n"
    )
    (sot_sample / "skills.yaml").write_text(
        "skills:\n  - id: s1\n    name: Skill\n    keywords: [one]\n"
    )
    (sot_sample / "education.yaml").write_text(
        "education:\n  - id: e1\n    institution: Inst\n    area: Area\n    tags: [core]\n"
    )
    (sot_sample / "letters.yaml").write_text(
        "letters:\n  - id: base\n    title: Base\n    salutation: Hello\n    closing: Thanks\n    sections:\n      - id: intro\n        text: Text\n        tags: [core]\n"
    )
    return sot_sample


def test_workflow_plain_renders_selected_recipe(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "workflow",
            "--plain",
            "--id",
            "baseline.build_preview",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "selected: baseline.build_preview" in output
    assert "recipe_id: baseline.build_preview" in output
    assert _recipe_command("build --variant base --format md,pdf", config_path=config_path) in output


def test_workflow_json_filters_recipe(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "workflow",
            "--json",
            "--id",
            "context.refresh",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "workflow"
    assert [recipe["id"] for recipe in payload["recipes"]] == ["context.refresh"]
    assert payload["sot"]["status"] == "ready"


def test_workflow_json_supports_automation_verify_recipe(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "workflow",
            "--json",
            "--id",
            "automation.verify",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [recipe["id"] for recipe in payload["recipes"]] == ["automation.verify"]
    assert payload["recipes"][0]["steps"][2]["command"] == _recipe_command(
        "preview --variant base --once",
        config_path=config_path,
    )


def test_workflow_json_keeps_external_config_for_review_import_recipe(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "workflow",
            "--json",
            "--id",
            "review.import",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["recipes"][0]["steps"][0]["command"] == _recipe_command(
        "reviewpack --variant base",
        config_path=config_path,
    )


def test_workflow_json_uses_project_selector_for_variant_manage_recipe(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "workflow",
            "--json",
            "--id",
            "variant.manage",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    steps = payload["recipes"][0]["steps"]
    assert steps[1]["command"] == _recipe_command(
        "variant keep --project <project-id> --id <variant-id>",
        config_path=config_path,
    )
    assert steps[2]["command"] == _recipe_command(
        "variant discard --project <project-id> --yes",
        config_path=config_path,
    )


def test_workflow_json_supports_local_bootstrap_recipe(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config_path.write_text(
        config_path.read_text().replace(
            "  sot: ../sot.sample\n",
            "  sot: ../local/sot\n",
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "workflow",
            "--json",
            "--id",
            "bootstrap.local_workspace",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [recipe["id"] for recipe in payload["recipes"]] == ["bootstrap.local_workspace"]
    assert payload["recipes"][0]["steps"][0]["command"] == _init_command(
        sample_default=False,
        workspace_root=tmp_path,
    )


def test_workflow_compact_json_is_recipe_focused(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "workflow",
            "--json",
            "--compact",
            "--id",
            "automation.verify",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "workflow"
    assert payload["sot"]["status"] == "ready"
    assert "files" not in payload["sot"]
    assert payload["recipes"][0]["steps"][0]["kind"] == "command"
    assert payload["recipes"][0]["steps"][0]["runnable"] is True
    assert payload["recipes"][0]["steps"][0]["placeholders"] == []


def test_workflow_compact_rejects_plain_output(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "workflow",
            "--plain",
            "--compact",
            "--id",
            "automation.verify",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 2
    assert "--compact requires --json" in strip_ansi(result.stderr)


def test_workflow_json_preserves_explicit_recipe_context(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = _write_minimal_sot(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "workflow",
            "--json",
            "--id",
            "automation.verify",
            "--config",
            str(config_path),
            "--sot-path",
            str(sot_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    recipe = payload["recipes"][0]
    assert recipe["steps"][0]["command"] == _recipe_command(
        "status",
        config_path=config_path,
        sot_path=sot_path,
    )
    assert recipe["steps"][2]["command"] == _recipe_command(
        "preview --variant base --once",
        config_path=config_path,
        sot_path=sot_path,
    )


def test_workflow_json_uses_project_runner_when_cwd_has_no_pyproject(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "workflow",
            "--json",
            "--id",
            "automation.verify",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    recipe = payload["recipes"][0]
    expected_prefix = f"uv run --project {Path(__file__).resolve().parents[2]} cvw "
    assert recipe["steps"][0]["command"].startswith(expected_prefix)
