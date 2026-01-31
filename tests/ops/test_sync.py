"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/ops/test_sync.py

Tests site sync behavior.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.cli import app
from tests.utils import strip_ansi


def test_sync_local_updates_site(tmp_path: Path) -> None:
    site_repo = tmp_path / "site"
    (site_repo / "src/content/cv").mkdir(parents=True)
    (site_repo / "public/cv").mkdir(parents=True)
    (site_repo / "src/content/page-cv").mkdir(parents=True)

    (site_repo / "src/content/cv/cv.md").write_text("old\n")
    (site_repo / "public/cv/cv.pdf").write_bytes(b"old")
    (site_repo / "src/content/page-cv/cv.md").write_text("---\ncvPdf: /cv/old.pdf\n---\ncontent\n")

    dist_dir = tmp_path / "var" / "dist" / "base"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "cv.md").write_text("new\n")
    (dist_dir / "cv.pdf").write_bytes(b"new")

    site_config = tmp_path / "site-sync.yaml"
    site_config.write_text(
        "\n".join(
            [
                "site:",
                f"  repo_path: {site_repo}",
                "  publish_variant: base",
                "  cv_markdown: src/content/cv/cv.md",
                "  cv_pdf_dir: public/cv",
                "  cv_pdf_name: cv.pdf",
                "  cv_page: src/content/page-cv/cv.md",
                "  cv_page_frontmatter_key: cvPdf",
            ]
        )
        + "\n"
    )
    workbench_config = tmp_path / "workbench.yaml"
    workbench_config.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: var/dist",
                "  runs: var/runs",
                "  sot: local/sot",
                "variants:",
                "  default: base",
                "site:",
                "  sync_mode: local",
            ]
        )
        + "\n"
    )
    variants_dir = tmp_path / "variants"
    variants_dir.mkdir()
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
    publish_config = tmp_path / "publish.yaml"
    publish_config.write_text(
        "\n".join(
            [
                "publish:",
                "  variants:",
                "    - base",
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
            "local",
            "--config",
            str(workbench_config),
            "--site-config",
            str(site_config),
        ],
    )

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "sync_mode: local" in output
    assert "pdf_url: /cv/cv.pdf" in output
    assert (site_repo / "src/content/cv/cv.md").read_text() == "new\n"
    assert (site_repo / "public/cv/cv.pdf").read_bytes() == b"new"
    assert "cvPdf: /cv/cv.pdf" in (site_repo / "src/content/page-cv/cv.md").read_text()


def test_sync_defaults_to_config_mode(tmp_path: Path) -> None:
    site_repo = tmp_path / "site"
    (site_repo / "src/content/cv").mkdir(parents=True)
    (site_repo / "public/cv").mkdir(parents=True)
    (site_repo / "src/content/page-cv").mkdir(parents=True)

    (site_repo / "src/content/cv/cv.md").write_text("old\n")
    (site_repo / "public/cv/cv.pdf").write_bytes(b"old")
    (site_repo / "src/content/page-cv/cv.md").write_text("---\ncvPdf: /cv/old.pdf\n---\ncontent\n")

    dist_dir = tmp_path / "var" / "dist" / "base"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "cv.md").write_text("new\n")
    (dist_dir / "cv.pdf").write_bytes(b"new")

    site_config = tmp_path / "site-sync.yaml"
    site_config.write_text(
        "\n".join(
            [
                "site:",
                f"  repo_path: {site_repo}",
                "  publish_variant: base",
                "  cv_markdown: src/content/cv/cv.md",
                "  cv_pdf_dir: public/cv",
                "  cv_pdf_name: cv.pdf",
                "  cv_page: src/content/page-cv/cv.md",
                "  cv_page_frontmatter_key: cvPdf",
            ]
        )
        + "\n"
    )

    workbench_config = tmp_path / "workbench.yaml"
    workbench_config.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: var/dist",
                "  runs: var/runs",
                "  sot: local/sot",
                "variants:",
                "  default: base",
                "site:",
                "  sync_mode: local",
            ]
        )
        + "\n"
    )
    variants_dir = tmp_path / "variants"
    variants_dir.mkdir()
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
    publish_config = tmp_path / "publish.yaml"
    publish_config.write_text(
        "\n".join(
            [
                "publish:",
                "  variants:",
                "    - base",
            ]
        )
        + "\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "sync",
            "--config",
            str(workbench_config),
            "--site-config",
            str(site_config),
        ],
    )

    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "sync_mode: local" in output


def test_sync_fails_when_repo_path_missing(tmp_path: Path) -> None:
    site_repo = tmp_path / "missing-site"

    dist_dir = tmp_path / "var" / "dist" / "base"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "cv.md").write_text("new\n")
    (dist_dir / "cv.pdf").write_bytes(b"new")

    site_config = tmp_path / "site-sync.yaml"
    site_config.write_text(
        "\n".join(
            [
                "site:",
                f"  repo_path: {site_repo}",
                "  publish_variant: base",
                "  cv_markdown: src/content/cv/cv.md",
                "  cv_pdf_dir: public/cv",
                "  cv_pdf_name: cv.pdf",
                "  cv_page: src/content/page-cv/cv.md",
                "  cv_page_frontmatter_key: cvPdf",
            ]
        )
        + "\n"
    )

    workbench_config = tmp_path / "workbench.yaml"
    workbench_config.write_text(
        "\n".join(
            [
                "paths:",
                "  dist: var/dist",
                "  runs: var/runs",
                "  sot: local/sot",
                "variants:",
                "  default: base",
                "site:",
                "  sync_mode: local",
            ]
        )
        + "\n"
    )
    variants_dir = tmp_path / "variants"
    variants_dir.mkdir()
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
    publish_config = tmp_path / "publish.yaml"
    publish_config.write_text(
        "\n".join(
            [
                "publish:",
                "  variants:",
                "    - base",
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
            "local",
            "--config",
            str(workbench_config),
            "--site-config",
            str(site_config),
        ],
    )

    assert result.exit_code != 0
    assert "Site repo path not found" in strip_ansi(result.stderr)
