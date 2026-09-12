"""Follow-up recipes must use the inspected workspace, not checkout defaults."""

import shlex

import yaml
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.ops.scaffold import init_project
from cvworkbench.workspace.workflows.review import review_import_recipe
from cvworkbench.workspace.workflows.setup import (
    bootstrap_sample_workspace_recipe,
    repair_sot_path_recipe,
)


def test_sample_recovery_uses_explicit_sample_with_an_existing_broken_config(tmp_path):
    init_project(tmp_path, sample_default=True)
    config = tmp_path / "config/workbench.yaml"
    data = yaml.safe_load(config.read_text())
    data["paths"]["sot"] = "../missing"
    config.write_text(yaml.safe_dump(data))
    recipe = bootstrap_sample_workspace_recipe(
        config_path=config,
        workspace_root=tmp_path,
        configured_sot_path=str(tmp_path / "missing"),
        sample_sot_path=tmp_path / "sot.sample",
        variant_label="base",
    )
    command = shlex.split(recipe["steps"][1]["command"])
    result = CliRunner().invoke(app, command[command.index("cvw") + 1 :])
    assert result.exit_code == 0
    assert '"status": "ready"' in result.stdout
    assert "--sot-path" in recipe["steps"][2]["command"]


def test_review_recipe_resolves_redirected_review_and_draft_stores(tmp_path):
    init_project(tmp_path)
    config = tmp_path / "config/workbench.yaml"
    data = yaml.safe_load(config.read_text())
    data["paths"]["reviews"] = "../review copies"
    data["paths"]["drafts"] = "../edit drafts"
    config.write_text(yaml.safe_dump(data))
    recipe = review_import_recipe(
        config_path=config,
        sot_path=tmp_path / "local/sot",
        configured_sot_path=None,
        variant_label="base",
    )
    command = shlex.split(recipe["steps"][2]["command"])
    assert command[command.index("--from") + 1] == str(tmp_path / "review copies/base/cv.docx")
    assert str(tmp_path / "review copies/base/cv.docx") in recipe["outputs"]
    assert not any("var/drafts" in value for value in recipe["outputs"])


def test_repair_recipe_names_the_selected_configuration(tmp_path):
    config = tmp_path / "another workspace/settings.yaml"
    recipe = repair_sot_path_recipe(config_path=config, configured_sot_path="missing")
    assert shlex.split(recipe["steps"][1]["command"]) == ["edit", str(config)]
    assert str(config) in recipe["outputs"]
