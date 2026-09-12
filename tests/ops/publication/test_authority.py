"""Verify publication uses the selected configuration and consumed input generation."""

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from cvworkbench.cli import app
from cvworkbench.ops.publication import pdf as publication
from cvworkbench.ops.publication.pdf import PublicPdfError, prepare_public_pdf
from cvworkbench.ops.syncing import sync_site
from tests.ops.publication.test_pdf import _write_docx, _write_pdf
from tests.ops.publication.test_state import _prepare
from tests.ops.test_sync import _write_workspace as _write_sync_workspace


def _change_settings_after_capture(monkeypatch, config, mutation):
    read_bytes = Path.read_bytes

    def read_then_change(path):
        content = read_bytes(path)
        if path == config:
            if mutation == "edit":
                data = yaml.safe_load(content)
                data["paths"]["publish"] = "../other-publication"
                data["paths"]["reviews"] = "../other-reviews"
                path.write_text(yaml.safe_dump(data))
            else:
                path.unlink()
        return content

    monkeypatch.setattr(Path, "read_bytes", read_then_change)


@pytest.mark.parametrize("mutation", ["edit", "remove"])
@pytest.mark.parametrize("entrypoint", ["api", "cli"])
def test_preparation_uses_one_workbench_configuration(tmp_path, monkeypatch, mutation, entrypoint):
    config, docx, pdf, policy, sot = _prepare(tmp_path)
    expected = tmp_path / "var/publish/base/cv.pdf"
    before = expected.read_bytes()
    _change_settings_after_capture(monkeypatch, config, mutation)

    if entrypoint == "api":
        result = prepare_public_pdf(
            authored_source=docx,
            source_pdf=pdf,
            config_path=config,
            variant_id="base",
            publish_config_path=policy,
            sot_path=sot,
        )
        output, review = result.output_pdf, result.review_path
    else:
        result = CliRunner().invoke(
            app,
            [
                "prepare-public-pdf",
                "--authored-source",
                str(docx),
                "--source-pdf",
                str(pdf),
                "--config",
                str(config),
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)["data"]
        output, review = Path(data["output_pdf"]), Path(data["review"])

    assert output == expected
    assert output.read_bytes() == before
    assert review.is_relative_to(tmp_path / "var/reviews/publication")
    assert not (tmp_path / "other-publication").exists()
    assert not (tmp_path / "other-reviews").exists()


@pytest.mark.parametrize("changed", ["policy", "variant", "person", "authored", "export"])
def test_preparation_rejects_input_changes_without_replacing_prepared_artifacts(
    tmp_path, monkeypatch, changed
):
    config, docx, pdf, policy, sot = _prepare(tmp_path)
    outputs = tmp_path / "var"
    before = {p: p.read_bytes() for p in outputs.rglob("*") if p.is_file()}
    target = {
        "policy": policy,
        "variant": config.parent / "variants/base.yaml",
        "person": sot / "person.yaml",
        "authored": docx,
        "export": pdf,
    }[changed]
    hook = (
        "_validate_authored_source"
        if changed in {"authored", "export"}
        else "publication_review_files"
    )
    original = getattr(publication, hook)

    def change_after_use(*args, **kwargs):
        result = original(*args, **kwargs)
        if changed == "authored":
            _write_docx(target, "An unrelated career document with different information")
        elif changed == "export":
            _write_pdf(target, ["An unrelated exported document with different information"])
        else:
            target.write_text(target.read_text() + "\n# independently revised input\n")
        return result

    monkeypatch.setattr(publication, hook, change_after_use)

    with pytest.raises(PublicPdfError, match="inputs changed during preparation"):
        prepare_public_pdf(
            authored_source=docx,
            source_pdf=pdf,
            config_path=config,
            variant_id="base",
            publish_config_path=policy,
            sot_path=sot,
        )

    assert {p: p.read_bytes() for p in outputs.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("cancel", [False, True])
def test_preparation_copies_are_private_temporary_and_keep_original_provenance(
    tmp_path, monkeypatch, cancel
):
    config, docx, pdf, policy, sot = _prepare(tmp_path)
    original = publication._validate_authored_source
    copies = []

    def observe_copies(authored, exported):
        assert authored != docx and exported != pdf
        assert authored.read_bytes() == docx.read_bytes()
        assert exported.read_bytes() == pdf.read_bytes()
        root = authored.parent.parent
        assert root.stat().st_mode & 0o777 == 0o700
        copies.extend(p for p in root.rglob("*") if p.is_file())
        assert len(copies) == 5
        assert all(p.stat().st_mode & 0o777 == 0o600 for p in copies)
        if cancel:
            raise KeyboardInterrupt
        return original(authored, exported)

    monkeypatch.setattr(publication, "_validate_authored_source", observe_copies)

    def prepare():
        return prepare_public_pdf(
            authored_source=docx,
            source_pdf=pdf,
            config_path=config,
            variant_id="base",
            publish_config_path=policy,
            sot_path=sot,
        )

    if cancel:
        with pytest.raises(KeyboardInterrupt):
            prepare()
    else:
        result = prepare()
        record = json.loads((result.output_pdf.parent / "preparation.json").read_text())
        for name, path in {
            "authored_source": docx,
            "exported_pdf": pdf,
            "policy": policy,
            "variant_config": config.parent / "variants/base.yaml",
            "person": sot / "person.yaml",
        }.items():
            assert record[name]["path"] == str(path.resolve())
    assert copies
    assert all(not path.exists() for path in copies)


@pytest.mark.parametrize("mutation", ["edit", "remove"])
@pytest.mark.parametrize("entrypoint", ["api", "cli"])
def test_sync_uses_one_workbench_configuration(tmp_path, monkeypatch, mutation, entrypoint):
    site, config, site_config = _write_sync_workspace(tmp_path)
    expected = (tmp_path / "var/publish/base/cv.pdf").read_bytes()
    _change_settings_after_capture(monkeypatch, config, mutation)

    if entrypoint == "api":
        result = sync_site(config_path=config, site_config_path=site_config, mode="local")
        assert result.mode == "local"
    else:
        result = CliRunner().invoke(
            app, ["sync", "--config", str(config), "--site-config", str(site_config), "--json"]
        )
        assert result.exit_code == 0, result.output

    assert (site / "public/cv/cv.pdf").read_bytes() == expected
    manifest = json.loads((site / "scripts/cv/public-cv-manifest.json").read_text())
    assert "authored_source" not in manifest
    assert not (tmp_path / "other-publication").exists()
