"""Verify review-conversion failures leave no partially registered import."""

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from cvworkbench.build.pipeline import build_documents
from cvworkbench.cli import app
from cvworkbench.ops.review.packs import build_review_pack


def test_normalization_failure_preserves_the_draft_inventory(sample_workspace, monkeypatch):
    config = Path("config/workbench.yaml")
    built = build_documents(
        sot_path=Path("sot.sample"), config_path=config, variant_id="base", formats=["pdf", "docx"]
    )
    pack = build_review_pack(config_path=config, variant_id="base", run=str(built.run_dir))
    retained = Path("var/drafts/retained/note.md")
    retained.parent.mkdir(parents=True)
    retained.write_text("Keep this independent draft.\n")

    def inventory():
        return {
            str(p): p.read_bytes() if p.is_file() else None for p in Path("var/drafts").rglob("*")
        }

    before = inventory()
    original_run = subprocess.run
    failures = []

    def fail_normalization(args, *positional, **kwargs):
        if "markdown+fenced_divs" in args:
            failures.append(args)
            return subprocess.CompletedProcess(
                args, 2, stdout="", stderr="Controlled normalization failure"
            )
        return original_run(args, *positional, **kwargs)

    monkeypatch.setattr(subprocess, "run", fail_normalization)
    result = CliRunner().invoke(
        app, ["import-docx", "--from", str(pack.docx_path), "--variant", "base", "--json"]
    )
    assert result.exit_code == 1
    assert not result.stdout
    assert "Controlled normalization failure" in result.stderr
    assert len(failures) == 1
    assert inventory() == before
