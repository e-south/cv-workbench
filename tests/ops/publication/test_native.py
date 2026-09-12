"""Native builds cross the same disclosure, freshness, and review boundary."""

import hashlib
import json

import pymupdf
import pytest
import yaml

from cvworkbench.inputs.sot import REQUIRED_FILES, load_sot_snapshot
from cvworkbench.ops.publication.native import prepare_native_public_pdf
from cvworkbench.ops.publication.pdf import PublicPdfError
from cvworkbench.ops.publication.state import inspect_publication, record_publication_review
from cvworkbench.ops.syncing import SyncError, sync_site
from tests.ops.publication.test_pdf import _write_workspace


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_workspace(root, *, with_html=True):
    config, variant, policy, sot = _write_workspace(root)
    for name in REQUIRED_FILES:
        if not (sot / name).exists():
            (sot / name).write_text("{}\n")
    run = root / "var/runs/build/example"
    run.mkdir(parents=True)
    markdown = "# Example Person\n\n[Email](mailto:person@example.com) [Paper](https://example.org/paper)\n"
    (run / "cv.md").write_text(markdown)
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Example Person\nEmail\nPaper", fontsize=11)
        for label, url in [
            ("Email", "mailto:person@example.com"),
            ("Paper", "https://example.org/paper"),
        ]:
            page.insert_link(
                {"kind": pymupdf.LINK_URI, "from": page.search_for(label)[0], "uri": url}
            )
        pdf.save(run / "cv.pdf")
    manifest = {
        "configuration": {"sha256": digest(config)},
        "variant": yaml.safe_load(variant.read_text())["variant"],
        "variant_hash": digest(variant),
        "sot_hashes": dict(load_sot_snapshot(sot).sot_hashes),
        "snippet_hashes": {},
        "outputs": {"pdf": "cv.pdf", "md": "cv.md"},
        "output_hashes": {fmt: digest(run / f"cv.{fmt}") for fmt in ("pdf", "md")},
    }
    if with_html:
        (run / "styles").mkdir()
        (run / "styles/theme.css").write_text(
            "body{font-family:Arial}.entry-heading>p{display:flex}"
        )
        (run / "cv.html").write_text(
            '<!doctype html><html><head><meta charset="utf-8"></head><body><h1>Example Person</h1><div class="contact-block"><p><a href="mailto:person@example.com">Email</a></p></div><div class="entry-heading"><p>Institute <span class="entry-date">2026</span></p></div></body></html>'
        )
        manifest["outputs"]["html"] = "cv.html"
        manifest["output_hashes"]["html"] = digest(run / "cv.html")
        manifest["render"] = {
            "formats": {
                "html": {
                    "style_path": "styles/theme.css",
                    "style_hash": digest(run / "styles/theme.css"),
                }
            }
        }
    (run / "manifest.json").write_text(json.dumps(manifest))
    return dict(
        run_path=run,
        config_path=config,
        variant_id="base",
        publish_config_path=policy,
        sot_path=sot,
    )


def test_native_prepare_review_sync_keeps_provenance_private(tmp_path):
    args = native_workspace(tmp_path)
    result = prepare_native_public_pdf(**args)
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["artifact_kind"] == "native-pdf-publication"
    assert "authored_name" not in manifest["source"]
    reading = manifest["reading_html"]
    html_path = result.output_pdf.parent / reading["name"]
    assert reading["sha256"] == digest(html_path)
    assert "<h1>Example Person</h1>" in html_path.read_text()
    assert "mailto:person@example.com" in html_path.read_text()
    assert 'charset="utf-8"' in html_path.read_text()
    assert 'class="contact-block"' in html_path.read_text()
    assert ".entry-heading>p{display:flex}" in html_path.read_text()
    assert str(tmp_path) not in result.manifest_path.read_text()
    config = args["config_path"]
    assert inspect_publication(config, "base").state == "review_required"
    site = tmp_path / "site"
    (site / "public/cv").mkdir(parents=True)
    (site / "page.md").write_text("---\ncvPdf: /old.pdf\n---\n")
    site_config = config.parent / "site-sync.yaml"
    site_config.write_text(
        yaml.safe_dump(
            {
                "site": {
                    "repo_path": str(site),
                    "publish_variant": "base",
                    "cv_pdf_dir": "public/cv",
                    "cv_pdf_name": "cv.pdf",
                    "cv_html": "content/cv.html",
                    "cv_manifest": "public/cv/manifest.json",
                    "cv_page": "page.md",
                    "cv_page_frontmatter_key": "cvPdf",
                }
            }
        )
    )
    with pytest.raises(SyncError, match="review_required"):
        sync_site(config_path=config, site_config_path=site_config, mode="local")
    record_publication_review(config, "base", digest(result.output_pdf))
    sync_site(config_path=config, site_config_path=site_config, mode="local")
    assert (site / "public/cv/cv.pdf").read_bytes() == result.output_pdf.read_bytes()
    assert str(tmp_path) not in (site / "public/cv/manifest.json").read_text()
    assert (site / "content/cv.html").read_bytes() == html_path.read_bytes()
    public_manifest = json.loads((site / "public/cv/manifest.json").read_text())
    assert public_manifest["html_sha256"] == digest(html_path)
    assert public_manifest["html_path"] == "content/cv.html"
    html_path.write_text("tampered")
    assert inspect_publication(config, "base").state == "invalid"
    before = {p: p.read_bytes() for p in site.rglob("*") if p.is_file()}
    with pytest.raises(SyncError):
        sync_site(config_path=config, site_config_path=site_config, mode="local")
    assert all(p.read_bytes() == data for p, data in before.items())
    assert not list(site.rglob("preparation.json"))


def test_native_preparation_rejects_midflight_source_change_and_preserves_prior_packet(
    tmp_path, monkeypatch
):
    import cvworkbench.ops.publication.native as native

    args = native_workspace(tmp_path)
    result = prepare_native_public_pdf(**args)
    original = native.publication_review_files
    prior = {
        p: p.read_bytes()
        for parent in (result.output_pdf.parent, result.review_path.parent)
        for p in parent.iterdir()
        if p.is_file()
    }

    def change_source(content, **kwargs):
        (args["sot_path"] / "experience.yaml").write_text("changed: true")
        return original(content, **kwargs)

    monkeypatch.setattr(native, "publication_review_files", change_source)
    with pytest.raises(ValueError, match="changed"):
        prepare_native_public_pdf(**args)
    assert all(p.read_bytes() == content for p, content in prior.items())


def test_native_workflow_routes_back_to_native_preparation(tmp_path):
    from cvworkbench.workspace.publication import publication_recipe

    args = native_workspace(tmp_path)
    prepare_native_public_pdf(**args)
    (args["run_path"] / "cv.pdf").write_bytes(b"changed")
    state = inspect_publication(args["config_path"], "base")
    recipe = publication_recipe(state, config_path=args["config_path"], command_prefix=["cvw"])
    assert recipe["id"] == "native.publish"
    assert any("publication prepare --run" in x["command"] for x in recipe["steps"])
    assert all("authored-source" not in x["command"] for x in recipe["steps"])


def test_native_section_rules_require_an_exact_approved_graphics_fingerprint(tmp_path):
    from cvworkbench.ops.publication.pdf import PublicPdfError, _visual_fingerprint

    args = native_workspace(tmp_path)
    run = args["run_path"]
    with pymupdf.open(run / "cv.pdf") as pdf:
        pdf[0].draw_line((72, 150), (510, 150), width=0.45)
        pdf.saveIncr()
        fingerprint = _visual_fingerprint(pdf)
    manifest = json.loads((run / "manifest.json").read_text())
    manifest["output_hashes"]["pdf"] = digest(run / "cv.pdf")
    (run / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(PublicPdfError):
        prepare_native_public_pdf(**args)
    policy = yaml.safe_load(args["publish_config_path"].read_text())
    policy["publish"]["approved_visual_fingerprint_sha256"] = fingerprint
    args["publish_config_path"].write_text(yaml.safe_dump(policy))
    result = prepare_native_public_pdf(**args)
    with pymupdf.open(result.output_pdf) as pdf:
        assert _visual_fingerprint(pdf) == fingerprint


def test_native_named_bookmark_must_resolve_inside_the_document(tmp_path):
    args = native_workspace(tmp_path)
    run = args["run_path"]
    with pymupdf.open(run / "cv.pdf") as pdf:
        pdf.set_toc([[1, "Experience", 1]])
        xref = pdf.get_toc(False)[0][3]["xref"]
        page_xref = pdf.page_xref(0)
        pdf.xref_set_key(
            pdf.pdf_catalog(),
            "Names",
            f"<</Dests <</Names [(experience) [{page_xref} 0 R /XYZ 72 150 0]]>>>>",
        )
        pdf.xref_set_key(xref, "A", "<</S /GoTo /D (experience)>>")
        pdf.saveIncr()
    m = json.loads((run / "manifest.json").read_text())
    m["output_hashes"]["pdf"] = digest(run / "cv.pdf")
    (run / "manifest.json").write_text(json.dumps(m))
    result = prepare_native_public_pdf(**args)
    with pymupdf.open(result.output_pdf) as pdf:
        assert pdf.get_toc(False)[0][3]["page"] == 0


def test_public_link_label_excludes_adjacent_unlinked_punctuation(tmp_path):
    args = native_workspace(tmp_path)
    run = args["run_path"]
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Paper, followed by context.", fontsize=14)
        page.insert_link(
            {
                "kind": pymupdf.LINK_URI,
                "from": page.search_for("Paper")[0],
                "uri": "https://example.org/paper",
            }
        )
        pdf.save(run / "cv.pdf")
    m = json.loads((run / "manifest.json").read_text())
    m["output_hashes"]["pdf"] = digest(run / "cv.pdf")
    (run / "manifest.json").write_text(json.dumps(m))
    result = prepare_native_public_pdf(**args)
    with pymupdf.open(result.output_pdf) as pdf:
        assert pdf[0].get_links()[0]["uri"] == "https://example.org/paper"


def test_native_export_timestamps_are_removed_without_mistaking_them_for_phone_numbers(tmp_path):
    args = native_workspace(tmp_path)
    run = args["run_path"]
    with pymupdf.open(run / "cv.pdf") as pdf:
        pdf.set_metadata({"creationDate": "D:20260911165536-04'00'"})
        pdf.saveIncr()
    m = json.loads((run / "manifest.json").read_text())
    m["output_hashes"]["pdf"] = digest(run / "cv.pdf")
    (run / "manifest.json").write_text(json.dumps(m))
    result = prepare_native_public_pdf(**args)
    with pymupdf.open(result.output_pdf) as pdf:
        assert not pdf.metadata["creationDate"]


def test_native_publication_cannot_replace_its_source_run(tmp_path):
    args = native_workspace(tmp_path)
    run = args["run_path"].with_name("base")
    args["run_path"].rename(run)
    args["run_path"] = run
    config = yaml.safe_load(args["config_path"].read_text())
    config["paths"]["publish"] = str(run.parent)
    args["config_path"].write_text(yaml.safe_dump(config))
    m = json.loads((run / "manifest.json").read_text())
    m["configuration"]["sha256"] = digest(args["config_path"])
    (run / "manifest.json").write_text(json.dumps(m))
    before = {p.relative_to(run): p.read_bytes() for p in run.rglob("*") if p.is_file()}
    with pytest.raises(RuntimeError, match="overlap"):
        prepare_native_public_pdf(**args)
    assert {p.relative_to(run): p.read_bytes() for p in run.rglob("*") if p.is_file()} == before


def test_native_publication_removes_automatic_opening_view_actions(tmp_path):
    args = native_workspace(tmp_path)
    run = args["run_path"]
    with pymupdf.open(run / "cv.pdf") as pdf:
        pdf.xref_set_key(pdf.pdf_catalog(), "OpenAction", f"[{pdf.page_xref(0)} 0 R /Fit]")
        pdf.saveIncr()
    m = json.loads((run / "manifest.json").read_text())
    m["output_hashes"]["pdf"] = digest(run / "cv.pdf")
    (run / "manifest.json").write_text(json.dumps(m))
    result = prepare_native_public_pdf(**args)
    with pymupdf.open(result.output_pdf) as pdf:
        assert pdf.xref_get_key(pdf.pdf_catalog(), "OpenAction")[0] == "null"
        assert "OpenAction" not in pdf.xref_get_keys(pdf.pdf_catalog())
    assert b"/OpenAction" not in result.output_pdf.read_bytes()


@pytest.mark.parametrize(
    "field, phase",
    [
        ("person.yaml", "stale_source"),
        ("experience.yaml", "stale_source"),
        ("cv.pdf", "stale_export"),
        ("cv.md", "stale_export"),
        ("manifest.json", "stale_export"),
        ("workbench.yaml", "stale_configuration"),
    ],
)
def test_native_review_expires_when_inputs_change(tmp_path, field, phase):
    args = native_workspace(tmp_path)
    result = prepare_native_public_pdf(**args)
    record_publication_review(args["config_path"], "base", digest(result.output_pdf))
    path = (
        args["config_path"]
        if field == "workbench.yaml"
        else args["sot_path"] / field
        if field.endswith(".yaml")
        else args["run_path"] / field
    )
    path.write_bytes(path.read_bytes() + b"\n ")
    assert inspect_publication(args["config_path"], "base").state == phase


@pytest.mark.parametrize(
    "mutation",
    ["phone", "foreign-link", "markdown-hash", "source-hash", "unsafe-output", "wrong-run"],
)
def test_native_prepare_rejects_disclosure_and_unbound_inputs_without_replacement(
    tmp_path, mutation
):
    args = native_workspace(tmp_path)
    result = prepare_native_public_pdf(**args)
    before = result.output_pdf.read_bytes()
    run = args["run_path"]
    if mutation in {"phone", "foreign-link"}:
        with pymupdf.open(run / "cv.pdf") as pdf:
            if mutation == "phone":
                pdf.set_metadata({"subject": "555.867.5309"})
            else:
                link = pdf[0].get_links()[0]
                pdf[0].update_link({**link, "uri": "https://example.org/undeclared"})
            pdf.saveIncr()
        m = json.loads((run / "manifest.json").read_text())
        m["output_hashes"]["pdf"] = digest(run / "cv.pdf")
        (run / "manifest.json").write_text(json.dumps(m))
    elif mutation == "markdown-hash":
        (run / "cv.md").write_text("Unbound edit")
    elif mutation == "source-hash":
        (args["sot_path"] / "experience.yaml").write_text("changed: true")
    elif mutation == "wrong-run":
        args["run_path"] = tmp_path
    else:
        m = json.loads((run / "manifest.json").read_text())
        m["outputs"]["pdf"] = "../cv.pdf"
        (run / "manifest.json").write_text(json.dumps(m))
    with pytest.raises((ValueError, RuntimeError)):
        prepare_native_public_pdf(**args)
    assert result.output_pdf.read_bytes() == before


@pytest.mark.parametrize("relative", ["cv.html", "styles/theme.css"])
def test_native_reading_requires_exact_rendered_html_and_styles(tmp_path, relative):
    args = native_workspace(tmp_path)
    result = prepare_native_public_pdf(**args)
    prior = result.output_pdf.read_bytes()
    (args["run_path"] / relative).write_text("changed")
    assert inspect_publication(args["config_path"], "base").state == "stale_export"
    with pytest.raises(PublicPdfError, match="hash"):
        prepare_native_public_pdf(**args)
    assert result.output_pdf.read_bytes() == prior


def test_native_pdf_only_run_does_not_invent_a_reading_layout(tmp_path):
    args = native_workspace(tmp_path, with_html=False)
    result = prepare_native_public_pdf(**args)
    assert json.loads(result.manifest_path.read_text())["reading_html"] is None
    assert not result.output_pdf.with_suffix(".html").exists()
