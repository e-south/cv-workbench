"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/cli/test_publication.py

Tests publication status, explicit review, and context workflow discovery.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import json

from typer.testing import CliRunner

from cvworkbench.cli import app
from tests.ops.publication.test_state import _prepare


def test_native_publication_cli_prepares_an_explicit_build(tmp_path):
    from tests.ops.publication.test_native import native_workspace

    args = native_workspace(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "publication",
            "prepare",
            "--run",
            str(args["run_path"]),
            "--config",
            str(args["config_path"]),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["command"] == "publication.prepare"
    state = CliRunner().invoke(
        app, ["publication", "status", "--config", str(args["config_path"]), "--json"]
    )
    assert json.loads(state.output)["publication"]["state"] == "review_required"


def test_publication_default_does_not_follow_the_generated_document_default(tmp_path):
    config, *_ = _prepare(tmp_path)
    config.write_text(config.read_text().replace("default: base", "default: cover-letter"))
    result = CliRunner().invoke(app, ["publication", "status", "--config", str(config), "--json"])
    assert result.exit_code == 0, result.output
    state = json.loads(result.output)["publication"]
    assert state["variant"] == "base"
    assert state["state"] == "review_required"


def test_publication_cli_and_context_expose_current_source_and_manual_review(tmp_path):
    config, docx, *_ = _prepare(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["publication", "status", "--config", str(config), "--json"])
    assert result.exit_code == 0, result.output
    state = json.loads(result.output)["publication"]
    assert state["state"] == "review_required"
    assert state["authored_source"] == str(docx.resolve())
    for compact in ([], ["--compact"]):
        context = runner.invoke(app, ["context", "--config", str(config), "--json", *compact])
        assert context.exit_code == 0, context.output
        payload = json.loads(context.output)
        assert payload["publication"]["state"] == "review_required"
        assert "authored.publish" in [item["id"] for item in payload["recipes"]]
    workflow = runner.invoke(
        app, ["workflow", "--id", "authored.publish", "--config", str(config), "--json"]
    )
    assert workflow.exit_code == 0, workflow.output
    assert '"kind": "manual"' in workflow.output
    assert '"runnable": false' in workflow.output
    reviewed = runner.invoke(
        app,
        [
            "publication",
            "review",
            "--config",
            str(config),
            "--pdf-sha256",
            state["pdf_sha256"],
            "--json",
        ],
    )
    assert reviewed.exit_code == 0, reviewed.output
    assert json.loads(reviewed.output)["publication"]["state"] == "reviewed"
