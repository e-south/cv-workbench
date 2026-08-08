"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/test_repository_contracts.py

Validates repository automation and agent-facing documentation contracts.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PINNED_ACTION = re.compile(r"^\s*-?\s*uses:\s*[^@\s]+@([0-9a-f]{40})(?:\s+#.*)?$")


def test_workflows_use_least_privilege_and_immutable_action_pins() -> None:
    workflows = sorted((ROOT / ".github/workflows").glob("*.yml"))

    assert {path.name for path in workflows} == {"ci.yml", "codeql.yml"}
    for workflow in workflows:
        contents = workflow.read_text()
        uses_lines = [line for line in contents.splitlines() if "uses:" in line]
        assert uses_lines
        assert all(PINNED_ACTION.match(line) for line in uses_lines)
        assert "permissions:" in contents
        assert "contents: read" in contents
        assert "timeout-minutes:" in contents
        assert "concurrency:" in contents

    codeql = (ROOT / ".github/workflows/codeql.yml").read_text()
    assert "security-events: write" in codeql
    assert "languages: python, actions" in codeql
    assert "queries: security-extended" in codeql

    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "dependency-audit:" in ci
    assert "uv run pip-audit" in ci
    assert "--no-install-recommends lmodern pandoc texlive-fonts-recommended texlive-xetex" in ci
    assert "kpsewhich lmroman10-regular.otf" in ci
    assert "kpsewhich pzdr.tfm" in ci


def test_dependabot_covers_python_and_workflow_dependencies() -> None:
    config = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())
    ecosystems = {entry["package-ecosystem"] for entry in config["updates"]}

    assert ecosystems == {"uv", "pre-commit", "github-actions"}


def test_pull_request_template_routes_human_and_codex_review() -> None:
    template = (ROOT / ".github/PULL_REQUEST_TEMPLATE.md").read_text()

    assert "private Source of Truth" in template
    assert "publication boundary" in template
    assert "@codex review" in template


def test_live_documentation_has_unique_agent_routing_frontmatter() -> None:
    documents = [ROOT / "docs/readme.md"]
    for section in ("concepts", "howto", "reference"):
        documents.extend(sorted((ROOT / "docs" / section).glob("*.md")))

    ids: list[str] = []
    for document in documents:
        text = document.read_text()
        assert text.startswith("---\n"), document
        _, frontmatter, _ = text.split("---", 2)
        metadata = yaml.safe_load(frontmatter)
        assert isinstance(metadata["id"], str)
        assert isinstance(metadata["intent"], str)
        assert metadata["audience"]
        assert metadata["status"] in {"active", "historical"}
        assert isinstance(metadata["navigation"]["parent"], str)
        ids.append(metadata["id"])

    assert len(ids) == len(set(ids))


def test_scoped_agent_routes_keep_private_and_documentation_rules_local() -> None:
    docs_rules = (ROOT / "docs/AGENTS.md").read_text()
    ops_rules = (ROOT / "src/cvworkbench/ops/AGENTS.md").read_text()

    assert "frontmatter" in docs_rules
    assert "progressive disclosure" in docs_rules
    assert "publication boundary" in ops_rules
    assert "fail closed" in ops_rules
