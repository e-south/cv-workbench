"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_context.py

Tests context command output.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import importlib
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
    sot_path = root / "sot.sample"
    sot_path.mkdir(parents=True, exist_ok=True)
    (sot_path / "person.yaml").write_text("id: sample\nname: Sample\n")
    (sot_path / "experience.yaml").write_text(
        "roles:\n  - id: role\n    company: Co\n    title: Title\n    start: 2020\n    bullets:\n      - id: b1\n        text: Did work\n        tags: [core]\n"
    )
    (sot_path / "projects.yaml").write_text(
        "projects:\n  - id: p1\n    name: Project\n    summary: Summary\n    tags: [core]\n"
    )
    (sot_path / "skills.yaml").write_text(
        "skills:\n  - id: s1\n    name: Skill\n    keywords: [one]\n"
    )
    (sot_path / "education.yaml").write_text(
        "education:\n  - id: e1\n    institution: Inst\n    area: Area\n    tags: [core]\n"
    )
    (sot_path / "letters.yaml").write_text(
        "letters:\n  - id: base\n    title: Base\n    salutation: Hello\n    closing: Thanks\n    sections:\n      - id: intro\n        text: Text\n        tags: [core]\n"
    )
    return sot_path


def test_context_reports_missing_sot_and_recipes(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "context",
            "--json",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "context"
    assert payload["sot"]["status"] == "missing"
    assert payload["variants"]["config_count"] == 1
    assert payload["recipes"]
    recipe_ids = [recipe["id"] for recipe in payload["recipes"]]
    assert recipe_ids[:4] == [
        "repair.sot_path",
        "baseline.build_preview",
        "automation.verify",
        "review.import",
    ]
    assert "project.guide" in recipe_ids
    for recipe in payload["recipes"][:4]:
        assert "preconditions" in recipe
        assert "steps" in recipe
        assert "outputs" in recipe
        assert "stop_conditions" in recipe
        assert recipe["steps"]
        assert "command" in recipe["steps"][0]
    repair_recipe = next(recipe for recipe in payload["recipes"] if recipe["id"] == "repair.sot_path")
    assert repair_recipe["steps"][0]["command"] == _recipe_command(
        "validate --sot-path <path-to-sot>",
        config_path=config_path,
    )
    review_recipe = next(recipe for recipe in payload["recipes"] if recipe["id"] == "review.import")
    assert any("import-docx --from " in step["command"] for step in review_recipe["steps"])


def test_context_omits_sot_path_in_recipes_when_configured_sot_is_ready(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "sot.sample"
    sot_path.mkdir()
    (sot_path / "person.yaml").write_text("id: sample\nname: Sample\n")
    (sot_path / "experience.yaml").write_text(
        "roles:\n  - id: role\n    company: Co\n    title: Title\n    start: 2020\n    bullets:\n      - id: b1\n        text: Did work\n        tags: [core]\n"
    )
    (sot_path / "projects.yaml").write_text(
        "projects:\n  - id: p1\n    name: Project\n    summary: Summary\n    tags: [core]\n"
    )
    (sot_path / "skills.yaml").write_text("skills:\n  - id: s1\n    name: Skill\n    keywords: [one]\n")
    (sot_path / "education.yaml").write_text(
        "education:\n  - id: e1\n    institution: Inst\n    area: Area\n    tags: [core]\n"
    )
    (sot_path / "letters.yaml").write_text(
        "letters:\n  - id: base\n    title: Base\n    salutation: Hello\n    closing: Thanks\n    sections:\n      - id: intro\n        text: Text\n        tags: [core]\n"
    )
    config_path.write_text(
        config_path.read_text().replace(
            "  reviews: ../var/reviews\n",
            "  reviews: ../var/reviews\n  sot: ../sot.sample\n",
        )
    )

    runner = CliRunner()
    result = runner.invoke(app, ["context", "--json", "--config", str(config_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    baseline = next(recipe for recipe in payload["recipes"] if recipe["id"] == "baseline.build_preview")
    assert baseline["steps"][0]["command"] == _recipe_command("status", config_path=config_path)
    assert baseline["steps"][1]["command"] == _recipe_command(
        "build --variant base --format md,pdf",
        config_path=config_path,
    )
    automation = next(recipe for recipe in payload["recipes"] if recipe["id"] == "automation.verify")
    assert automation["steps"][2]["command"] == _recipe_command(
        "preview --variant base --once",
        config_path=config_path,
    )


def test_context_compact_json_is_summary_only_and_guided(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)
    config_path.write_text(
        config_path.read_text().replace(
            "  reviews: ../var/reviews\n",
            "  reviews: ../var/reviews\n  sot: ../sot.sample\n",
        )
    )

    runner = CliRunner()
    result = runner.invoke(app, ["context", "--json", "--compact", "--config", str(config_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "context"
    assert payload["sot"]["status"] == "ready"
    assert "files" not in payload["sot"]
    assert "latest_by_variant" not in payload["runs"]
    assert payload["recommended_workflows"][0]["id"] == "automation.verify"
    assert payload["recommended_workflows"][0]["command"] == _workflow_command(
        "automation.verify",
        config_path=config_path,
    )
    assert payload["recommended_workflows"][0]["json_command"] == _workflow_command(
        "automation.verify",
        config_path=config_path,
        json_output=True,
        compact=True,
    )
    assert payload["recipes"][0] == {
        "id": "baseline.build_preview",
        "title": "Baseline build and preview",
    }


def test_context_recipe_steps_expose_machine_actionable_metadata(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["context", "--json", "--config", str(config_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    repair_recipe = next(recipe for recipe in payload["recipes"] if recipe["id"] == "repair.sot_path")
    repair_validate_step = repair_recipe["steps"][0]
    repair_edit_step = repair_recipe["steps"][1]

    assert repair_validate_step["kind"] == "command"
    assert repair_validate_step["runnable"] is False
    assert repair_validate_step["placeholders"] == ["<path-to-sot>"]
    assert repair_edit_step["kind"] == "manual"
    assert repair_edit_step["runnable"] is False
    assert repair_edit_step["placeholders"] == []

    review_recipe = next(recipe for recipe in payload["recipes"] if recipe["id"] == "review.import")
    review_edit_step = review_recipe["steps"][1]
    assert review_edit_step["kind"] == "manual"
    assert review_edit_step["runnable"] is False
    assert review_edit_step["placeholders"] == ["<variant>"]


def test_bootstrap_json_matches_compact_context_payload(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)
    config_path.write_text(
        config_path.read_text().replace(
            "  reviews: ../var/reviews\n",
            "  reviews: ../var/reviews\n  sot: ../sot.sample\n",
        )
    )

    runner = CliRunner()
    result = runner.invoke(app, ["bootstrap", "--json", "--config", str(config_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "bootstrap"
    assert payload["sot"]["status"] == "ready"
    assert payload["recommended_workflows"][0]["id"] == "automation.verify"
    assert payload["recommended_workflows"][0]["json_command"] == _workflow_command(
        "automation.verify",
        config_path=config_path,
        json_output=True,
        compact=True,
    )
    assert "latest_by_variant" not in payload["runs"]


def test_bootstrap_plain_focuses_on_next_workflows(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)
    config_path.write_text(
        config_path.read_text().replace(
            "  reviews: ../var/reviews\n",
            "  reviews: ../var/reviews\n  sot: ../sot.sample\n",
        )
    )

    runner = CliRunner()
    result = runner.invoke(app, ["bootstrap", "--plain", "--config", str(config_path)])

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "next_workflows:" in output
    assert "automation.verify" in output
    assert "next_commands:" in output
    assert "recipes:" not in output


def test_context_compact_matches_full_shared_fields(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)
    config_path.write_text(
        config_path.read_text().replace(
            "  reviews: ../var/reviews\n",
            "  reviews: ../var/reviews\n  sot: ../sot.sample\n",
        )
    )

    run_dir = tmp_path / "var" / "runs" / "2026-01-01T00-00-00Z"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-01-01T00:00:00+00:00",
                "formats": ["md"],
                "outputs": {"md": "cv.md"},
                "variant": {"id": "base"},
            }
        )
        + "\n"
    )
    (tmp_path / "var" / "runs" / "2026-01-02T00-00-00Z").mkdir(parents=True, exist_ok=True)

    project_dir = tmp_path / "var" / "projects" / "demo"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: demo",
                "  base_variant: base",
                "  sot_path: ../sot.sample",
            ]
        )
        + "\n"
    )

    review_dir = tmp_path / "var" / "reviews" / "base"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "review.md").write_text("review\n")

    runner = CliRunner()
    full_result = runner.invoke(app, ["context", "--json", "--config", str(config_path)])
    compact_result = runner.invoke(app, ["context", "--json", "--compact", "--config", str(config_path)])

    assert full_result.exit_code == 0
    assert compact_result.exit_code == 0
    full_payload = json.loads(full_result.stdout)
    compact_payload = json.loads(compact_result.stdout)

    assert compact_payload["sot"]["status"] == full_payload["sot"]["status"]
    assert compact_payload["sot"]["files_summary"] == full_payload["sot"]["files_summary"]
    assert compact_payload["sot"]["sections_summary"] == full_payload["sot"]["sections_summary"]
    assert compact_payload["sot"]["tags_summary"] == full_payload["sot"]["tags_summary"]
    assert compact_payload["sot"]["versions_summary"] == full_payload["sot"]["versions_summary"]
    assert compact_payload["variants"]["default"] == full_payload["variants"]["default"]
    assert compact_payload["variants"]["summary"] == full_payload["variants"]["summary"]
    assert compact_payload["variants"]["inbox_summary"] == full_payload["variants"]["inbox_summary"]
    assert compact_payload["runs"]["latest_summary"] == full_payload["runs"]["latest_summary"]
    assert compact_payload["runs"]["invalid_summary"] == full_payload["runs"]["invalid_summary"]
    assert compact_payload["projects"]["count"] == full_payload["projects"]["count"]
    assert compact_payload["projects"]["summary"] == full_payload["projects"]["summary"]
    assert compact_payload["projects"]["invalid_summary"] == full_payload["projects"]["invalid_summary"]
    assert compact_payload["reviews"]["count"] == full_payload["reviews"]["count"]
    assert compact_payload["reviews"]["summary"] == full_payload["reviews"]["summary"]
    assert compact_payload["recommended_workflows"] == full_payload["recommended_workflows"]
    assert [recipe["id"] for recipe in compact_payload["recipes"]] == [
        recipe["id"] for recipe in full_payload["recipes"]
    ]


def test_context_compact_limits_run_scan_to_latest(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)
    config_path.write_text(
        config_path.read_text().replace(
            "  reviews: ../var/reviews\n",
            "  reviews: ../var/reviews\n  sot: ../sot.sample\n",
        )
    )

    seen: dict[str, int] = {}

    def fake_latest_runs_by_variant(
        config_path: Path,
        *,
        limit: int = 3,
        include_project_runs: bool = False,
    ):
        seen["limit"] = limit
        seen["include_project_runs"] = int(include_project_runs)
        return {}, []

    app_module = importlib.import_module("cvworkbench.cli.app")
    monkeypatch.setattr(app_module, "latest_runs_by_variant", fake_latest_runs_by_variant)

    runner = CliRunner()
    result = runner.invoke(app, ["context", "--json", "--compact", "--config", str(config_path)])

    assert result.exit_code == 0
    assert seen["limit"] == 1
    assert seen["include_project_runs"] == 0


def test_context_uses_validated_payload_without_reloading_sot(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)
    config_path.write_text(
        config_path.read_text().replace(
            "  reviews: ../var/reviews\n",
            "  reviews: ../var/reviews\n  sot: ../sot.sample\n",
        )
    )

    app_module = importlib.import_module("cvworkbench.cli.app")

    def fail_load_sot(*_args, **_kwargs):
        raise AssertionError("context should not reload the SoT after validation")

    monkeypatch.setattr(app_module, "load_sot", fail_load_sot)

    runner = CliRunner()
    result = runner.invoke(app, ["context", "--json", "--config", str(config_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["sot"]["status"] == "ready"


def test_status_uses_validated_payload_without_reloading_sot(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)
    config_path.write_text(
        config_path.read_text().replace(
            "  reviews: ../var/reviews\n",
            "  reviews: ../var/reviews\n  sot: ../sot.sample\n",
        )
    )

    app_module = importlib.import_module("cvworkbench.cli.app")

    def fail_load_sot(*_args, **_kwargs):
        raise AssertionError("status should not reload the SoT after validation")

    monkeypatch.setattr(app_module, "load_sot", fail_load_sot)

    runner = CliRunner()
    result = runner.invoke(app, ["status", "--json", "--config", str(config_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["sot"]["path"] == str((tmp_path / "sot.sample").resolve())


def test_context_compact_rejects_plain_output(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["context", "--compact", "--plain", "--config", str(config_path)])

    assert result.exit_code == 2
    assert "--compact requires --json" in strip_ansi(result.stderr)


def test_context_compact_recommended_workflows_preserve_explicit_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    sot_path = _write_minimal_sot(tmp_path)
    external_cwd = tmp_path / "external"
    external_cwd.mkdir()
    monkeypatch.chdir(external_cwd)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "context",
            "--json",
            "--compact",
            "--config",
            str(config_path),
            "--sot-path",
            str(sot_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["recommended_workflows"][0]["command"] == _workflow_command(
        "automation.verify",
        config_path=config_path,
        sot_path=sot_path,
    )


def test_context_recipes_preserve_explicit_paths_when_supported(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    sot_path = _write_minimal_sot(tmp_path)
    external_cwd = tmp_path / "external"
    external_cwd.mkdir()
    monkeypatch.chdir(external_cwd)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "context",
            "--json",
            "--config",
            str(config_path),
            "--sot-path",
            str(sot_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)

    baseline = next(recipe for recipe in payload["recipes"] if recipe["id"] == "baseline.build_preview")
    assert baseline["steps"][0]["command"] == _recipe_command(
        "status",
        config_path=config_path,
        sot_path=sot_path,
    )
    assert baseline["steps"][1]["command"] == _recipe_command(
        "build --variant base --format md,pdf",
        config_path=config_path,
        sot_path=sot_path,
    )

    automation = next(recipe for recipe in payload["recipes"] if recipe["id"] == "automation.verify")
    assert automation["steps"][2]["command"] == _recipe_command(
        "preview --variant base --once",
        config_path=config_path,
        sot_path=sot_path,
    )

    review_recipe = next(recipe for recipe in payload["recipes"] if recipe["id"] == "review.import")
    assert review_recipe["steps"][0]["command"] == _recipe_command(
        "reviewpack --variant base",
        config_path=config_path,
    )
    assert review_recipe["steps"][2]["command"] == _recipe_command(
        "import-docx --from var/reviews/base/cv.docx --variant base",
        config_path=config_path,
    )
    assert review_recipe["steps"][3]["command"] == "edit var/drafts/import-*/notes.md"
    assert review_recipe["steps"][4]["command"] == _recipe_command(
        "apply --draft <draft-dir>",
        sot_path=sot_path,
    )

    project_recipe = next(recipe for recipe in payload["recipes"] if recipe["id"] == "project.guide")
    assert project_recipe["steps"][0]["command"] == _recipe_command(
        "project guide --job-file <job-file>",
        config_path=config_path,
        sot_path=sot_path,
    )
    assert project_recipe["steps"][1]["command"] == _recipe_command(
        "project show <project-id>",
        config_path=config_path,
    )
    assert project_recipe["steps"][2]["command"] == _recipe_command(
        "preview --project <project-id>",
        config_path=config_path,
        sot_path=sot_path,
    )
    assert project_recipe["steps"][3]["command"] == _recipe_command(
        "project apply <project-id>",
        config_path=config_path,
        sot_path=sot_path,
    )

    inspect_recipe = next(recipe for recipe in payload["recipes"] if recipe["id"] == "project.inspect")
    assert inspect_recipe["steps"][0]["command"] == _recipe_command(
        "project show <project-id>",
        config_path=config_path,
    )
    assert inspect_recipe["steps"][1]["command"] == _recipe_command(
        "preview --project <project-id>",
        config_path=config_path,
        sot_path=sot_path,
    )

    refresh_recipe = next(recipe for recipe in payload["recipes"] if recipe["id"] == "context.refresh")
    assert refresh_recipe["steps"][0]["command"] == _recipe_command(
        "context --json",
        config_path=config_path,
        sot_path=sot_path,
    )

    variant_recipe = next(recipe for recipe in payload["recipes"] if recipe["id"] == "variant.manage")
    assert variant_recipe["steps"][1]["command"] == _recipe_command(
        "variant keep --project <project-id> --id <variant-id>",
        config_path=config_path,
    )
    assert variant_recipe["steps"][2]["command"] == _recipe_command(
        "variant discard --project <project-id> --yes",
        config_path=config_path,
    )


def test_context_project_recipe_keeps_placeholder_project_id(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    project_dir = tmp_path / "var" / "projects" / "demo"
    proposals_dir = project_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  id: demo",
                "  base_variant: base",
                "  sot_path: ../sot.sample",
            ]
        )
        + "\n"
    )
    (proposals_dir / "variant.yaml").write_text("variant:\n  id: demo\n")
    (proposals_dir / "patch.yaml").write_text("patch:\n  format: unified-diff\n  diff: \"\"\n")

    runner = CliRunner()
    result = runner.invoke(app, ["context", "--json", "--config", str(config_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    project_recipe = next(recipe for recipe in payload["recipes"] if recipe["id"] == "project.guide")
    assert project_recipe["steps"][1]["command"] == _recipe_command(
        "project show <project-id>",
        config_path=config_path,
    )
    assert project_recipe["steps"][2]["command"] == _recipe_command(
        "preview --project <project-id>",
        config_path=config_path,
    )
    assert project_recipe["steps"][3]["command"] == _recipe_command(
        "project apply <project-id>",
        config_path=config_path,
    )


def test_context_compact_recommends_sample_bootstrap_when_sample_exists(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    (tmp_path / "sot.sample").mkdir()

    runner = CliRunner()
    result = runner.invoke(app, ["context", "--json", "--compact", "--config", str(config_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["sot"]["status"] == "missing"
    assert payload["recommended_workflows"][0]["id"] == "bootstrap.sample_workspace"
    assert (
        payload["recommended_workflows"][0]["command"]
        == _workflow_command("bootstrap.sample_workspace", config_path=config_path)
    )


def test_context_includes_sample_bootstrap_recipe_when_sample_exists(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    (tmp_path / "sot.sample").mkdir()

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "context",
            "--json",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["sot"]["status"] == "missing"
    assert payload["recipes"][0]["id"] == "bootstrap.sample_workspace"
    assert payload["recipes"][0]["steps"][0]["command"] == _init_command(
        sample_default=True,
        workspace_root=tmp_path,
    )


def test_context_compact_recommends_local_bootstrap_when_local_sot_is_missing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config_path.write_text(
        config_path.read_text().replace(
            "paths:\n",
            "paths:\n  sot: ../local/sot\n",
        )
    )

    runner = CliRunner()
    compact_result = runner.invoke(app, ["context", "--json", "--compact", "--config", str(config_path)])
    full_result = runner.invoke(app, ["context", "--json", "--config", str(config_path)])

    assert compact_result.exit_code == 0
    assert full_result.exit_code == 0
    compact_payload = json.loads(compact_result.stdout)
    full_payload = json.loads(full_result.stdout)
    assert compact_payload["sot"]["status"] == "missing"
    assert compact_payload["recommended_workflows"][0]["id"] == "bootstrap.local_workspace"
    assert compact_payload["recommended_workflows"][0]["command"] == _workflow_command(
        "bootstrap.local_workspace",
        config_path=config_path,
    )
    local_recipe = next(recipe for recipe in full_payload["recipes"] if recipe["id"] == "bootstrap.local_workspace")
    assert local_recipe["steps"][0]["command"] == _init_command(
        sample_default=False,
        workspace_root=tmp_path,
    )


def test_context_recipes_preserve_external_config_for_review_and_project(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)
    sot_path = tmp_path / "sot.sample"
    config_path.write_text(
        config_path.read_text().replace(
            "  reviews: ../var/reviews\n",
            "  reviews: ../var/reviews\n  sot: ../sot.sample\n",
        )
    )

    runner = CliRunner()
    result = runner.invoke(app, ["context", "--json", "--config", str(config_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    review_recipe = next(recipe for recipe in payload["recipes"] if recipe["id"] == "review.import")
    assert review_recipe["steps"][0]["command"] == _recipe_command(
        "reviewpack --variant base",
        config_path=config_path,
    )
    assert review_recipe["steps"][2]["command"] == _recipe_command(
        "import-docx --from var/reviews/base/cv.docx --variant base",
        config_path=config_path,
    )
    assert review_recipe["steps"][3]["command"] == "edit var/drafts/import-*/notes.md"
    assert review_recipe["steps"][4]["command"] == _recipe_command(
        "apply --draft <draft-dir>",
        sot_path=sot_path,
    )
    project_recipe = next(recipe for recipe in payload["recipes"] if recipe["id"] == "project.guide")
    assert project_recipe["steps"][0]["command"] == _recipe_command(
        "project guide --job-file <job-file>",
        config_path=config_path,
    )
    assert project_recipe["steps"][1]["command"] == _recipe_command(
        "project show <project-id>",
        config_path=config_path,
    )
    assert project_recipe["steps"][2]["command"] == _recipe_command(
        "preview --project <project-id>",
        config_path=config_path,
    )


def test_context_recommended_workflows_skip_review_import_when_runs_are_not_review_ready(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)
    config_path.write_text(
        config_path.read_text().replace(
            "  reviews: ../var/reviews\n",
            "  reviews: ../var/reviews\n  sot: ../sot.sample\n",
        )
    )
    run_dir = tmp_path / "var" / "runs" / "2026-03-10T00-00-00Z"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-03-10T00:00:00+00:00",
                "formats": ["md"],
                "outputs": {"md": "cv.md"},
                "variant": {"id": "base"},
            }
        )
    )
    (run_dir / "cv.md").write_text("# cv\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["context", "--json", "--compact", "--config", str(config_path)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    recommended_ids = [item["id"] for item in payload["recommended_workflows"]]
    assert "review.import" not in recommended_ids
    assert "project.guide" in recommended_ids


def test_context_variant_run_inventory_ignores_newer_project_runs(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_minimal_sot(tmp_path)
    config_path.write_text(
        config_path.read_text().replace(
            "  reviews: ../var/reviews\n",
            "  reviews: ../var/reviews\n  sot: ../sot.sample\n",
        )
    )
    variant_run_dir = tmp_path / "var" / "runs" / "2026-03-09T00-00-00Z"
    variant_run_dir.mkdir(parents=True, exist_ok=True)
    (variant_run_dir / "selection.json").write_text("{\"items\": []}\n")
    (variant_run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-03-09T00:00:00+00:00",
                "formats": ["md", "pdf", "docx"],
                "outputs": {"md": "cv.md", "pdf": "cv.pdf", "docx": "cv.docx"},
                "variant": {"id": "base"},
            }
        )
    )
    project_run_dir = tmp_path / "var" / "runs" / "projects" / "job" / "2026-03-10T00-00-00Z"
    project_run_dir.mkdir(parents=True, exist_ok=True)
    (project_run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-03-10T00:00:00+00:00",
                "formats": ["md"],
                "outputs": {"md": "cv.md"},
                "variant": {"id": "base"},
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(app, ["context", "--json", "--config", str(config_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["runs"]["latest_by_variant"]["base"][0]["run_id"] == "2026-03-09T00-00-00Z"
    recommended_ids = [item["id"] for item in payload["recommended_workflows"]]
    assert "review.import" in recommended_ids


def test_context_invalid_sot_recommends_repair_workflow(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    sot_path = tmp_path / "sot.sample"
    sot_path.mkdir(parents=True, exist_ok=True)
    (sot_path / "person.yaml").write_text("id: sample\nname: Sample\n")
    (sot_path / "experience.yaml").write_text("roles: not-a-list\n")
    (sot_path / "projects.yaml").write_text("projects: []\n")
    (sot_path / "skills.yaml").write_text("skills: []\n")
    (sot_path / "education.yaml").write_text("education: []\n")
    (sot_path / "letters.yaml").write_text("letters: []\n")
    config_path.write_text(
        config_path.read_text().replace(
            "  reviews: ../var/reviews\n",
            "  reviews: ../var/reviews\n  sot: ../sot.sample\n",
        )
    )

    runner = CliRunner()
    result = runner.invoke(app, ["context", "--json", "--compact", "--config", str(config_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["recommended_workflows"][0]["id"] == "repair.sot_yaml"
    assert payload["recommended_workflows"][0]["id"] != "bootstrap.sample_workspace"
    workflow_result = runner.invoke(
        app,
        ["workflow", "--json", "--id", "repair.sot_yaml", "--config", str(config_path)],
    )
    assert workflow_result.exit_code == 0
    workflow_payload = json.loads(workflow_result.stdout)
    repair_recipe = workflow_payload["recipes"][0]
    assert repair_recipe["steps"][0]["command"] == _recipe_command(
        "validate",
        config_path=config_path,
    )


def test_context_plain_surfaces_recommended_workflows(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    (tmp_path / "sot.sample").mkdir()

    runner = CliRunner()
    result = runner.invoke(app, ["context", "--plain", "--config", str(config_path)])

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "next_workflows:" in output
    assert "next_commands:" in output
    assert "bootstrap.sample_workspace" in output


def test_context_strict_requires_sot(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "context",
            "--json",
            "--strict",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 1
