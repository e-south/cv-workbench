"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/dev/test_context_contract.py

Tests compact context docs/help contract for bootstrap usage.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app
from tests.utils import strip_ansi

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_context_help_exposes_compact_bootstrap_mode() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["context", "--help"])

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "--compact" in output
    assert "summary-only JSON output" in output
    assert "agent handoff" in output


def test_workflow_help_exposes_compact_recipe_mode() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["workflow", "--help"])

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "--compact" in output
    assert "recipe retrieval" in output
    assert "agent handoff" in output


def test_compact_bootstrap_docs_match_live_commands() -> None:
    readme = (REPO_ROOT / "README.md").read_text()
    quickstart = (REPO_ROOT / "docs" / "howto" / "quickstart.md").read_text()
    contract = (REPO_ROOT / "docs" / "reference" / "context-contract.md").read_text()

    assert "uv run cvw context --json --compact" in readme
    assert "uv run cvw workflow --id automation.verify" in readme
    assert "uv run cvw workflow --id automation.verify --json --compact" in readme
    assert "uv run python scripts/verify_repo.py" in readme
    assert "uv run cvw context --json --compact" in quickstart
    assert "uv run cvw workflow --id automation.verify" in quickstart
    assert "uv run cvw workflow --id automation.verify --json --compact" in quickstart
    assert "recommended_workflows" in contract
    assert "json_command" in contract
    assert "local bootstrap lane" in contract
    assert "repair.sot_path" in contract
    assert "repair.sot_yaml" in contract
    assert "uv run cvw context --json --compact" in contract
    assert "uv run cvw workflow --id <recipe-id> --json --compact" in contract


def test_verify_harness_docs_are_routed_from_readme_and_docs_index() -> None:
    readme = (REPO_ROOT / "README.md").read_text()
    docs_index = (REPO_ROOT / "docs" / "readme.md").read_text()
    contract = (REPO_ROOT / "docs" / "reference" / "verify-contract.md").read_text()

    assert "docs/reference/verify-contract.md" in readme
    assert "reference/verify-contract.md" in docs_index
    assert "uv run python scripts/verify_repo.py" in contract
    assert "fails fast" in contract


def test_sync_default_docs_are_consistent() -> None:
    quickstart = (REPO_ROOT / "docs" / "howto" / "quickstart.md").read_text()
    site_contract = (REPO_ROOT / "docs" / "reference" / "site-contract.md").read_text()
    journal = (REPO_ROOT / "docs" / "reference" / "journal.md").read_text()

    assert "defaults to local mode" in quickstart
    assert "defaults to local updates" in site_contract
    assert "current default is local-first sync" in journal


def test_project_review_docs_keep_build_before_reviewpack() -> None:
    quickstart = (REPO_ROOT / "docs" / "howto" / "quickstart.md").read_text()
    contract = (REPO_ROOT / "docs" / "reference" / "project-contract.md").read_text()

    assert "uv run cvw build --project <project-id> --format md,pdf,docx" in quickstart
    assert "uv run cvw reviewpack --project <project-id>" not in quickstart
    assert "latest review-ready" in contract
    assert "get the pinned `--run` command" in contract


def test_docs_make_bounded_editing_scope_explicit() -> None:
    readme = (REPO_ROOT / "README.md").read_text()
    overview = (REPO_ROOT / "docs" / "concepts" / "overview.md").read_text()
    contract = (REPO_ROOT / "docs" / "reference" / "project-contract.md").read_text()

    assert "free-form NL rewriting" in readme
    assert "GUI SoT editing" in readme
    assert "free-form NL rewriting" in contract
    assert "SoT" in contract
    assert "executable ops are intentionally narrow" in overview


def test_project_docs_surface_comparison_and_exact_url_keying() -> None:
    quickstart = (REPO_ROOT / "docs" / "howto" / "quickstart.md").read_text()
    ingestion = (REPO_ROOT / "docs" / "howto" / "ingestion.md").read_text()
    contract = (REPO_ROOT / "docs" / "reference" / "project-contract.md").read_text()

    assert "diff --artifact canonical --run-a <base-run-id-or-path>" in quickstart
    assert "projects/<project-id>/<run-id>" in quickstart
    assert "diff --artifact canonical --run-a <base-run>" in contract
    assert "Registry ids are keyed from the exact URL string" in ingestion
    assert "--job-file" in ingestion


def test_performance_docs_cover_preview_and_read_path_profiling() -> None:
    performance = (REPO_ROOT / "docs" / "howto" / "performance.md").read_text()

    assert "preview-once.prof" in performance
    assert "context.prof" in performance
    assert "project-show.prof" in performance
    assert "project show \\" in performance
