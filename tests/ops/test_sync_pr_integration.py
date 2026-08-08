"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_sync_pr_integration.py

Optional integration test for PR-based sync.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pymupdf
import pytest
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.ops.publish import load_publish_config
from cvworkbench.variants import load_variant


def _should_run() -> bool:
    if os.getenv("CVW_GH_SYNC_INTEGRATION") != "1":
        return False
    if not os.getenv("CVW_GH_SYNC_SITE"):
        return False
    if shutil.which("gh") is None:
        return False
    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


pytestmark = pytest.mark.skipif(
    not _should_run(),
    reason="Set CVW_GH_SYNC_INTEGRATION=1 and CVW_GH_SYNC_SITE to run.",
)


def test_sync_pr_creates_branch_and_pr(tmp_path: Path) -> None:
    site_repo = Path(os.environ["CVW_GH_SYNC_SITE"]).expanduser().resolve()
    assert site_repo.exists()

    _ensure_clean_repo(site_repo)
    original_branch = _git(site_repo, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()

    site_cv_page = site_repo / "src/content/page-cv/cv.md"
    if not site_cv_page.exists():
        pytest.fail(f"Missing site CV page: {site_cv_page}")

    publish_dir = Path("var/publish/base")
    publish_dir.mkdir(parents=True, exist_ok=True)
    variant = load_variant(Path("config/variants/base.yaml"))
    publish = load_publish_config(Path("config/publish.yaml"))
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), f"Sync integration test: {os.getpid()}")
    pdf_bytes = document.tobytes()
    document.close()
    (publish_dir / "cv.pdf").write_bytes(pdf_bytes)
    (publish_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_kind": "authored-pdf-publication",
                "variant": {
                    "id": "base",
                    "exclude_tags": variant.exclude_tags,
                    "contact_fields": variant.contact_fields,
                    "order": variant.order,
                },
                "formats": ["pdf"],
                "outputs": {"pdf": "cv.pdf"},
                "output_hashes": {"pdf": hashlib.sha256(pdf_bytes).hexdigest()},
                "source": {"visual_fingerprint_sha256": publish.approved_visual_fingerprint_sha256},
                "transformation": {
                    "kind": "semantic-redaction",
                    "forbidden_contact_fields": ["phone"],
                    "forbidden_sections": ["references"],
                    "redaction_count": 0,
                },
            }
        )
        + "\n"
    )

    site_config = tmp_path / "site-sync.yaml"
    site_config.write_text(
        "\n".join(
            [
                "site:",
                f"  repo_path: {site_repo}",
                "  publish_variant: base",
                "  cv_pdf_dir: public/cv",
                "  cv_pdf_name: cv.pdf",
                "  cv_manifest: scripts/cv/public-cv-manifest.json",
                "  cv_page: src/content/page-cv/cv.md",
                "  cv_page_frontmatter_key: cvPdf",
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "sync",
            "--mode",
            "pr",
            "--site-config",
            str(site_config),
        ],
    )

    assert result.exit_code == 0
    new_branch = _git(site_repo, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    assert new_branch.startswith("cv-update/")

    pr_list = subprocess.run(
        ["gh", "pr", "list", "--head", new_branch, "--limit", "1"],
        cwd=site_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert pr_list.returncode == 0
    assert pr_list.stdout.strip()

    _git(site_repo, ["switch", original_branch])


def _ensure_clean_repo(repo_path: Path) -> None:
    status = _git(repo_path, ["status", "--porcelain"]).strip()
    if status:
        pytest.fail("Site repo has uncommitted changes")


def _git(repo_path: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail((result.stderr or result.stdout or "").strip() or "Git command failed")
    return result.stdout
