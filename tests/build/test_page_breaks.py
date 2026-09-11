"""Explicit page starts preserve reading order across document formats."""

import subprocess
from pathlib import Path
from zipfile import ZipFile

import pymupdf
import pytest

from cvworkbench.build.rendering import resolve_filter_paths


def render(source, output):
    filters = Path(__file__).resolve().parents[2] / "build/filters"
    args = ["pandoc", "--pdf-engine=xelatex", "-o", str(output)]
    for path in resolve_filter_paths(filters):
        args.extend(["--lua-filter", str(path)])
    return subprocess.run(args, input=source, text=True, capture_output=True, check=True)


def test_page_starts_preserve_headings_and_text_in_pdf_docx_and_html(tmp_path):
    source = """---
cvw-page-break-before: [education]
---
## Experience

First page evidence.

## Education

Second page evidence.
"""
    pdf = tmp_path / "pages.pdf"
    render(source, pdf)
    with pymupdf.open(pdf) as doc:
        assert len(doc) == 2
        assert "First page evidence." in doc[0].get_text()
        assert doc[1].get_text().startswith("Education")
    docx = tmp_path / "pages.docx"
    render(source, docx)
    with ZipFile(docx) as z:
        xml = z.read("word/document.xml").decode()
    assert 'w:type="page"' in xml
    assert xml.index("First page evidence.") < xml.index('w:type="page"') < xml.index("Education")
    html = tmp_path / "pages.html"
    render(source, html)
    text = html.read_text()
    assert "break-before: page" in text
    assert text.index("First page evidence.") < text.index("Second page evidence.")
    render(source.replace("cvw-page-break-before: [education]", ""), pdf)
    with pymupdf.open(pdf) as doc:
        assert len(doc) == 1


@pytest.mark.parametrize("value", ["educaton", "[educaton]", "[education, education]"])
def test_page_starts_reject_invalid_or_unresolved_targets(tmp_path, value):
    with pytest.raises(subprocess.CalledProcessError) as error:
        render(
            f"---\ncvw-page-break-before: {value}\n---\n## Education\n\nDegree.\n",
            tmp_path / "out.html",
        )
    assert "cvw-page-break-before" in error.value.stderr


def test_variant_page_starts_do_not_affect_other_variants_and_survive_review(sample_workspace):
    import json

    import yaml

    from cvworkbench.build.pipeline import build_documents
    from cvworkbench.ops.review.importing import import_docx_review
    from cvworkbench.ops.review.packs import build_review_pack

    config = Path("config/workbench.yaml")
    variant_path = Path("config/variants/base.yaml")
    variant = yaml.safe_load(variant_path.read_text())
    variant["variant"]["order"] = ["experience", "education", "teaching"]
    variant["variant"]["render"] = {"page_break_before": ["education"]}
    variant_path.write_text(yaml.safe_dump(variant))
    teaching = {
        "teaching": [
            {
                "id": "autumn",
                "course": "BIO 101",
                "role": "Instructor",
                "term": "Fall 2024",
                "enrollment": 18,
                "evaluation": "4.5/5",
            },
            {
                "id": "spring",
                "course": "BIO 101",
                "role": "Instructor",
                "term": "Spring 2023",
                "enrollment": 27,
                "evaluation": "4.9/5",
            },
        ]
    }
    Path("sot.sample/teaching.yaml").write_text(yaml.safe_dump(teaching))
    defaults = Path("build/themes/default/pandoc/common.defaults.yaml")
    defaults.write_text(
        "standalone: true\nmetadata:\n  cvw-inline-teaching: true\n  cvw-concise-entries: true\n  cvw-aligned-entries: true\n  cvw-entry-structure: true\n"
    )
    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=config,
        variant_id="base",
        formats=["md", "pdf", "docx"],
    )
    with pymupdf.open(result.dist_dir / "cv.pdf") as doc:
        assert len(doc) == 2
        assert doc[1].get_text().startswith("Education")
        assert "18 students" in doc[1].get_text() and "27 students" in doc[1].get_text()
    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    assert manifest["variant"]["page_break_before"] == ["education"]
    pack = build_review_pack(config_path=config, variant_id="base", run=str(result.run_dir))
    imported = import_docx_review(
        docx_path=pack.docx_path, config_path=config, run=None, variant_id="base", project_dir=None
    )
    # Aligned/inline presentation differs from canonical Markdown. Keep that
    # review-only; never manufacture source edits from a layout transformation.
    assert imported.apply_status == "review_diff_only"
    assert imported.patch_path.name == "patch.diff"
    assert yaml.safe_load(Path("sot.sample/teaching.yaml").read_text()) == teaching
    variant["variant"]["id"] = "short"
    variant["variant"].pop("render")
    Path("config/variants/short.yaml").write_text(yaml.safe_dump(variant))
    shorter = build_documents(
        sot_path=Path("sot.sample"), config_path=config, variant_id="short", formats=["pdf"]
    )
    with pymupdf.open(shorter.dist_dir / "cv.pdf") as doc:
        assert len(doc) == 1


@pytest.mark.parametrize(
    "value", ["education", ["education", "education"], ["education\nother: true"], [3]]
)
def test_variant_page_starts_validate_ids(value):
    from cvworkbench.variants import parse_variant

    with pytest.raises(ValueError, match="page_break_before"):
        parse_variant(
            {"variant": {"id": "cv", "outputs": ["pdf"], "render": {"page_break_before": value}}}
        )


def test_page_start_ids_cannot_be_interpreted_as_yaml_mappings():
    from cvworkbench.variants import parse_variant

    with pytest.raises(ValueError, match="page_break_before"):
        parse_variant(
            {
                "variant": {
                    "id": "cv",
                    "outputs": ["pdf"],
                    "render": {"page_break_before": ["education:"]},
                }
            }
        )
