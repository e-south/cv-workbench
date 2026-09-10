"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_docx_reference.py

Verifies theme-owned DOCX styles and generated package integrity.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import subprocess
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import yaml

from cvworkbench.build.pipeline import execute_build
from cvworkbench.build.planning import plan_build
from cvworkbench.build.rendering import RenderError, render_document
from cvworkbench.themes import ThemeError, load_theme
from cvworkbench.variants import parse_variant


def _reference(sample_workspace):
    theme = sample_workspace / "build/themes/default"
    reference = theme / "reference.docx"
    subprocess.run(
        ["pandoc", "-f", "markdown", "-t", "docx", "-o", str(reference)],
        input="",
        text=True,
        capture_output=True,
        check=True,
    )
    with ZipFile(reference) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ET.register_namespace("w", namespace)
    styles = ET.fromstring(files["word/styles.xml"])
    normal = styles.find(f".//{{{namespace}}}style[@{{{namespace}}}styleId='Normal']")
    assert normal is not None
    properties = ET.SubElement(normal, f"{{{namespace}}}rPr")
    ET.SubElement(
        properties,
        f"{{{namespace}}}rFonts",
        {f"{{{namespace}}}ascii": "Arial", f"{{{namespace}}}hAnsi": "Arial"},
    )
    files["word/styles.xml"] = ET.tostring(styles, encoding="utf-8", xml_declaration=True)
    with ZipFile(reference, "w", ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    definition = theme / "theme.yaml"
    data = yaml.safe_load(definition.read_text())
    data["routes"]["docx"]["reference_doc"] = "reference.docx"
    definition.write_text(yaml.safe_dump(data))
    return theme, reference


def test_docx_route_uses_reference_styles_and_captures_asset(sample_workspace, tmp_path):
    _, reference = _reference(sample_workspace)
    plan = plan_build(
        sot_path=sample_workspace / "sot.sample",
        config_path=sample_workspace / "config/workbench.yaml",
        variant_id="base",
        formats=["docx"],
    )
    assert reference.resolve() in plan.render_assets.file_hashes
    result = execute_build(plan, run_dir=tmp_path / "run", dist_dir=tmp_path / "dist")
    with ZipFile(result.dist_dir / "cv.docx") as archive:
        assert b"Arial" in archive.read("word/styles.xml")
        for name in archive.namelist():
            if name.endswith((".xml", ".rels")):
                ET.fromstring(archive.read(name))


def test_reference_edit_rejected_before_output_writes(sample_workspace, tmp_path):
    _, reference = _reference(sample_workspace)
    plan = plan_build(
        sot_path=sample_workspace / "sot.sample",
        config_path=sample_workspace / "config/workbench.yaml",
        variant_id="base",
        formats=["docx"],
    )
    reference.write_bytes(reference.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="Render asset changed"):
        execute_build(plan, run_dir=tmp_path / "run", dist_dir=tmp_path / "dist")
    assert not (tmp_path / "run").exists() and not (tmp_path / "dist").exists()


@pytest.mark.parametrize(
    "route,value",
    [
        ("pdf", "reference.docx"),
        ("docx", "../outside.docx"),
        ("docx", "missing.docx"),
        ("docx", ""),
    ],
)
def test_reference_contract_rejects_invalid_routes_and_paths(sample_workspace, route, value):
    theme, _ = _reference(sample_workspace)
    definition = theme / "theme.yaml"
    data = yaml.safe_load(definition.read_text())
    data["routes"][route]["reference_doc"] = value
    definition.write_text(yaml.safe_dump(data))
    with pytest.raises(ThemeError, match="reference_doc"):
        load_theme(theme)


@pytest.mark.parametrize("invalid", ["malformed-xml", "missing-parts", "not-zip"])
def test_invalid_rendered_docx_preserves_previous_artifact(tmp_path, monkeypatch, invalid):
    source = tmp_path / "source.md"
    source.write_text("# Example\n")
    output = tmp_path / "cv.docx"
    output.write_bytes(b"previous artifact")

    def broken_writer(args):
        path = type(output)(args[args.index("--output") + 1])
        if invalid == "not-zip":
            path.write_bytes(b"not a document")
            return
        with ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types />")
            archive.writestr("word/document.xml", "<document />")
            if invalid == "malformed-xml":
                archive.writestr("word/styles.xml", "<styles><w:style /></styles>")

    monkeypatch.setattr("cvworkbench.build.rendering._run", broken_writer)
    variant = parse_variant({"variant": {"id": "base", "outputs": ["docx"]}})
    with pytest.raises(RenderError, match="Rendered DOCX"):
        render_document(source, output, variant, tmp_path, "docx", None, pandoc_path="pandoc")
    assert output.read_bytes() == b"previous artifact"
