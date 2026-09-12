"""Local document discovery and explicit promotion are public, portable commands."""

import json

from typer.testing import CliRunner

from cvworkbench.cli import app
from tests.ops.test_document_promotion import manual_request


def test_manual_cli_journey_requires_exact_review_and_does_not_expose_contents(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PRIVATE_TEST_CREDENTIAL", "never-print-this-value")
    request = manual_request(tmp_path, b"private-document-content")
    runner = CliRunner()
    listing = runner.invoke(app, ["documents", "list", "--root", str(tmp_path), "--json"])
    assert listing.exit_code == 0, listing.output
    assert len(json.loads(listing.output)["documents"]["items"]) == 1
    command = ["documents", "promote", "--root", str(tmp_path), "--request", str(request), "--json"]
    preview = runner.invoke(app, command)
    assert preview.exit_code == 0, preview.output
    assert not (tmp_path / "current").exists()
    missing = runner.invoke(app, command + ["--apply"])
    assert missing.exit_code != 0
    result = runner.invoke(
        app, command + ["--apply", "--reviewed-sha256", json.loads(preview.output)["plan_sha256"]]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "promoted"
    for output in [listing.output, preview.output, missing.output, result.output]:
        assert "never-print-this-value" not in output
        assert "private-document-content" not in output


def test_context_routes_to_library_without_changing_default_workspace(sample_workspace):
    config = sample_workspace / "config/workbench.yaml"
    config.write_text(config.read_text() + "\ndocuments:\n  root: ..\n")
    for flags in [[], ["--compact"]]:
        result = CliRunner().invoke(app, ["context", "--config", str(config), "--json", *flags])
        assert result.exit_code == 0, result.output
        documents = json.loads(result.output)["documents"]
        assert documents["root"] == str(sample_workspace)
        assert "documents list" in documents["list_command"]


def test_sync_uses_the_selected_external_workspace_site_config(tmp_path):
    from pathlib import Path

    import yaml

    from cvworkbench.ops.publication.native import prepare_native_public_pdf
    from cvworkbench.ops.publication.record import hash_file
    from cvworkbench.ops.publication.state import record_publication_review
    from tests.ops.publication.test_native import native_workspace

    args = native_workspace(tmp_path / "external")
    result = prepare_native_public_pdf(**args)
    record_publication_review(args["config_path"], "base", hash_file(result.output_pdf))
    site = tmp_path / "site"
    site.mkdir()
    (site / "cv.md").write_text("---\ncvPdf: /old.pdf\n---\n")
    (args["config_path"].parent / "site-sync.yaml").write_text(
        yaml.safe_dump(
            {
                "site": {
                    "repo_path": str(site),
                    "publish_variant": "base",
                    "cv_pdf_dir": "public/cv",
                    "cv_pdf_name": "cv.pdf",
                    "cv_manifest": "public/cv/manifest.json",
                    "cv_page": "cv.md",
                    "cv_page_frontmatter_key": "cvPdf",
                }
            }
        )
    )
    Path("config").mkdir()
    Path("config/site-sync.yaml").write_text("site: wrong-workspace\n")
    outcome = CliRunner().invoke(
        app, ["sync", "--config", str(args["config_path"]), "--mode", "local", "--json"]
    )
    assert outcome.exit_code == 0, outcome.output
    assert (site / "public/cv/cv.pdf").read_bytes() == result.output_pdf.read_bytes()
