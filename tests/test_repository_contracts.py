"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/test_repository_contracts.py

Validates repository automation and agent-facing documentation contracts.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PINNED_ACTION = re.compile(r"^\s*-?\s*uses:\s*[^@\s]+@([0-9a-f]{40})(?:\s+#.*)?$")


def test_default_pytest_discovery_includes_every_test_bearing_file() -> None:
    expected = set()
    for path in (ROOT / "tests").rglob("test_*.py"):
        nodes = ast.walk(ast.parse(path.read_text()))
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
            for node in nodes
        ):
            expected.add(path.relative_to(ROOT).as_posix())

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts="],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    collected = {
        line.split("::", 1)[0]
        for line in result.stdout.splitlines()
        if line.startswith("tests/") and "::" in line
    }
    assert expected <= collected, (
        f"Default pytest omitted test files: {sorted(expected - collected)}"
    )


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


def test_readme_banner_uses_package_safe_absolute_url() -> None:
    readme = (ROOT / "README.md").read_text()

    assert readme.startswith(
        "# ![cv-workbench deterministic CV toolkit]("
        "https://raw.githubusercontent.com/e-south/cv-workbench/main/"
        "assets/cv-workbench-banner.svg)\n"
    )


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
    test_rules = (ROOT / "tests/AGENTS.md").read_text()

    assert "frontmatter" in docs_rules
    assert "progressive disclosure" in docs_rules
    assert "publication boundary" in ops_rules
    assert "fail closed" in ops_rules
    assert "sample_workspace" in test_rules
    assert "../docs/reference/verify-contract.md#test-workspaces" in test_rules


def test_docs_router_links_to_canonical_configuration_and_sample_sources() -> None:
    router = ROOT / "docs/readme.md"
    text = router.read_text()
    links = dict(re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text))
    for path in (
        "config/workbench.yaml",
        "config/publish.yaml",
        "config/site-sync.yaml",
        "config/variants/base.yaml",
        "build/themes/default/theme.yaml",
        "sot.sample/",
    ):
        assert (router.parent / links[path]).resolve() == (ROOT / path).resolve()
    assert "local/sot/" not in links


def test_build_recovery_contract_routes_to_distinct_owners() -> None:
    architecture = (ROOT / "docs/concepts/architecture.md").read_text()
    contract = (ROOT / "docs/reference/configuration-contract.md").read_text()
    assert "configuration-contract.md#build-bundle-recovery" in architecture
    for owner in ("build/planning.py", "build/artifacts.py", "build/pipeline.py", "storage.py"):
        assert owner in architecture
        assert (ROOT / "src/cvworkbench" / owner).is_file()
    assert "### Build bundle recovery" in contract
    assert "tests/build/test_bundle_recovery.py" in contract
    assert "tests/test_storage.py" in contract
    assert "not simultaneous visibility" in contract


def test_preview_ownership_contract_routes_paths_and_retention() -> None:
    preview = (ROOT / "docs/reference/preview-contract.md").read_text()
    retention = (ROOT / "docs/reference/artifact-retention.md").read_text()
    verification = (ROOT / "docs/reference/verify-contract.md").read_text()
    assert "## Artifact ownership" in preview
    assert "dev/preview_paths.py" in preview
    assert "artifact-retention.md#preview-artifacts" in preview
    assert "## Preview Artifacts" in retention
    assert "preview-contract.md#artifact-ownership" in retention
    assert "audited_build_artifacts: preserved" in verification
    assert "var/dist/<variant>/cv.html" not in (ROOT / "docs/howto/styling.md").read_text()


def test_render_asset_contract_routes_fingerprints_and_limits() -> None:
    contract = (ROOT / "docs/reference/configuration-contract.md").read_text()
    architecture = (ROOT / "docs/concepts/architecture.md").read_text()
    styling = (ROOT / "docs/howto/styling.md").read_text()
    assert "### Render asset lifetime" in contract
    assert "build/assets.py::capture_render_assets" in contract
    assert "`render.filters`" in contract
    assert "Transient edits reverted between checks can go undetected" in contract
    assert "`build/assets.py`" in architecture
    assert "configuration-contract.md#render-asset-lifetime" in styling


def test_project_run_recovery_has_one_allocation_and_storage_contract() -> None:
    project = (ROOT / "docs/reference/project-contract.md").read_text()
    storage = (ROOT / "docs/reference/configuration-contract.md").read_text()
    architecture = (ROOT / "docs/concepts/architecture.md").read_text()
    assert "build/runs.py::allocate_run" in project
    assert "exception notes and CLI stderr" in project
    assert "configuration-contract.md#build-bundle-recovery" in project
    assert "`new_directories`" in storage
    assert "Existing directory modes" in storage
    assert "`build/runs.py`" in architecture


def test_patch_application_routes_its_shared_execution_and_recovery_contract() -> None:
    contract = (ROOT / "docs/reference/patch-application.md").read_text()
    assert "`ops/patches.py`" in contract
    assert "`delete_paths`" in contract
    assert "inherited umask" in contract
    assert "not writer" in contract
    for relative in (
        "docs/readme.md",
        "docs/reference/project-contract.md",
        "docs/reference/review-contract.md",
        "docs/reference/configuration-contract.md",
        "src/cvworkbench/ops/AGENTS.md",
    ):
        assert "patch-application.md" in (ROOT / relative).read_text()


def test_proposal_authoring_routes_its_owner_and_recovery_contract() -> None:
    contract = (ROOT / "docs/reference/project-contract.md").read_text()
    rules = (ROOT / "src/cvworkbench/ops/projects/AGENTS.md").read_text()
    assert "### Proposal authoring" in contract
    assert "patches.py::read_project_patch_document" in contract
    assert "`patch_authoring.py`" in contract
    assert "configuration-contract.md#build-bundle-recovery" in contract
    assert "tests/ops/test_project_patch_authoring.py" in contract
    assert "project-contract.md#proposal-authoring" in rules


def test_contact_presentation_routes_one_owner_and_export_contract() -> None:
    styling = (ROOT / "docs/howto/styling.md").read_text()
    architecture = (ROOT / "docs/concepts/architecture.md").read_text()
    assert "## Contact presentation" in styling
    assert "build/contacts.py" in styling
    assert "tests/build/test_contacts.py" in styling
    assert "publication-contract.md" in styling
    assert "styling.md#contact-presentation" in architecture
