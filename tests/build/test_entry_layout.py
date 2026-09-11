"""Verify the reader-visible structure of generated record metadata and prose."""

import subprocess
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from xml.dom import minidom
from zipfile import ZipFile

import pymupdf
import pytest
import yaml

from cvworkbench.build.markdown import build_markdown
from cvworkbench.build.pipeline import build_documents
from cvworkbench.ops.review.importing import import_docx_review
from cvworkbench.ops.review.packs import build_review_pack
from cvworkbench.variants import load_variant


def _entry_html(section, item, variant):
    variant = replace(variant, order=[section])
    markdown = build_markdown({section: {section: [item]}}, variant)
    result = subprocess.run(
        ["pandoc", "--from", "markdown+fenced_divs", "--to", "html5"],
        input=markdown,
        text=True,
        capture_output=True,
        check=True,
    )
    return ET.fromstring("<root>" + result.stdout + "</root>").find("section")


@pytest.mark.parametrize(
    "section,item,paragraphs",
    [
        (
            "education",
            {
                "institution": "Example University",
                "study_type": "MSc",
                "area": "Biology",
                "location": "Example City",
                "start": 2020,
                "end": 2022,
                "advisors": ["A. Mentor", "B. Mentor"],
                "thesis_title": "A useful thesis",
                "highlights": ["Completed a research placement."],
            },
            [
                "MSc - Biology | Example City | 2020 — 2022",
                "Advisors: A. Mentor, B. Mentor",
                "Thesis: “A useful thesis”",
            ],
        ),
        (
            "publications",
            {
                "title": "A useful paper",
                "authors": [{"name": "Example Author"}],
                "venue": "Example Journal",
                "year": 2025,
                "notes": "Equal contribution.",
            },
            ["Example Author | Example Journal | 2025", "Equal contribution."],
        ),
        (
            "conferences",
            {
                "title": "A useful talk",
                "event": "Example Conference",
                "year": 2025,
                "presentation_type": "Talk",
                "notes": "Invited presentation.",
            },
            ["Talk | A useful talk | 2025", "Invited presentation."],
        ),
        (
            "honors",
            {
                "title": "Fellowship",
                "issuer": "Example Foundation",
                "year": 2025,
                "summary": "Supported a **research** placement.",
            },
            ["Example Foundation | 2025", "Supported a research placement."],
        ),
        (
            "service",
            {
                "role": "Mentor",
                "organization": "Example University",
                "start": 2024,
                "summary": "Mentored three students.",
            },
            ["Mentor | 2024 — Present", "Mentored three students."],
        ),
        (
            "teaching",
            {
                "course": "Biology",
                "role": "Instructor",
                "term": "Spring 2025",
                "enrollment": 40,
                "evaluation": "4.8/5.0",
                "summary": "Led seminars.",
            },
            ["Instructor | Enrollment: 40 | Evaluation: 4.8/5.0 | Spring 2025", "Led seminars."],
        ),
        (
            "references",
            {
                "name": "Example Mentor",
                "title": "Professor",
                "organization": "Example University",
                "relationship": "Advisor",
                "email": "mentor@example.com",
                "notes": "Available upon request.",
            },
            [
                "Professor | Example University | Advisor | mentor@example.com",
                "Available upon request.",
            ],
        ),
    ],
)
def test_entry_metadata_and_narrative_have_distinct_paragraphs(
    sample_workspace, section, item, paragraphs
):
    variant = load_variant(Path("config/variants/base.yaml"))
    entry = _entry_html(section, {"id": "example", "tags": ["core"], **item}, variant)
    assert entry is not None
    assert ["".join(p.itertext()) for p in entry.findall("p")] == paragraphs
    assert len(entry.findall("h3")) == 1
    assert entry.get("id").endswith("-example")
    if section == "education":
        assert ["".join(li.itertext()) for li in entry.findall("ul/li")] == [
            "Completed a research placement."
        ]


@pytest.mark.parametrize(
    "values,expected",
    [
        ({}, "Instructor"),
        ({"enrollment": 12}, "Instructor | Enrollment: 12"),
        ({"evaluation": "4.6/5"}, "Instructor | Evaluation: 4.6/5"),
    ],
)
def test_optional_teaching_metadata_has_no_empty_labels(sample_workspace, values, expected):
    variant = load_variant(Path("config/variants/base.yaml"))
    entry = _entry_html(
        "teaching",
        {"id": "example", "tags": ["core"], "course": "Biology", "role": "Instructor", **values},
        variant,
    )
    assert ["".join(p.itertext()) for p in entry.findall("p")] == [expected]


@pytest.mark.parametrize(
    "edit,expected_status",
    [("bullet", "ready"), ("none", "ready_no_changes"), ("link", "review_diff_only")],
)
def test_real_exports_keep_metadata_separate_and_reviewed_bullets_applyable(
    sample_workspace, edit, expected_status
):
    source = Path("sot.sample")
    before = {str(p): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    result = build_documents(
        sot_path=source,
        config_path=Path("config/workbench.yaml"),
        variant_id="base",
        formats=["md", "html", "pdf", "docx"],
    )
    with ZipFile(result.dist_dir / "cv.docx") as document:
        tree = ET.fromstring(document.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = ["".join(p.itertext()) for p in tree.findall(".//w:body/w:p", ns)]
    teaching_meta = next(p for p in paragraphs if "Enrollment:" in p)
    assert "Evaluation: 4.8/5.0" in teaching_meta
    assert "Led recitations" not in teaching_meta
    assert "Led recitations and mentored student projects." in paragraphs
    with pymupdf.open(result.dist_dir / "cv.pdf") as pdf:
        text = "\n".join(p.get_text() for p in pdf)
        assert "Enrollment: 40" in text and "Evaluation: 4.8/5.0" in text

    pack = build_review_pack(
        config_path=Path("config/workbench.yaml"), variant_id="base", run=str(result.run_dir)
    )
    role = yaml.safe_load((source / "experience.yaml").read_text())["roles"][0]
    bullet = role["bullets"][0]
    updated = "Delivered a measured improvement through careful engineering."
    with ZipFile(pack.docx_path) as document:
        entries = [(info, document.read(info.filename)) for info in document.infolist()]
    edited = 0
    with ZipFile(pack.docx_path, "w") as document:
        for info, contents in entries:
            if info.filename == "word/document.xml":
                tree = minidom.parseString(contents)
                for node in tree.getElementsByTagNameNS(ns["w"], "t"):
                    if (
                        edit == "bullet"
                        and node.firstChild is not None
                        and node.firstChild.nodeValue == bullet["text"]
                    ):
                        node.firstChild.nodeValue = updated
                        edited += 1
                contents = tree.toxml(encoding="utf-8")
            elif edit == "link" and info.filename == "word/_rels/document.xml.rels":
                tree = minidom.parseString(contents)
                for node in tree.getElementsByTagNameNS("*", "Relationship"):
                    if node.getAttribute("Target") == "https://github.com/example":
                        node.setAttribute("Target", "https://example.com/changed-destination")
                        edited += 1
                contents = tree.toxml(encoding="utf-8")
            document.writestr(info, contents)
    assert edited == (0 if edit == "none" else 1)
    imported = import_docx_review(
        docx_path=pack.docx_path,
        config_path=Path("config/workbench.yaml"),
        run=None,
        variant_id="base",
        project_dir=None,
    )
    assert imported.apply_status == expected_status
    if edit == "bullet":
        patch = yaml.safe_load(imported.patch_path.read_text())
        assert patch["patch"]["operations"] == [
            {
                "op": "replace-experience-bullet",
                "role_id": role["id"],
                "bullet_id": bullet["id"],
                "old_text": bullet["text"],
                "new_text": updated,
            }
        ]
    elif edit == "none":
        assert yaml.safe_load(imported.patch_path.read_text())["patch"]["operations"] == []
    else:
        assert imported.patch_path.name == "patch.diff"
        assert "https://example.com/changed-destination" in imported.patch_path.read_text()
    assert {str(p): p.read_bytes() for p in source.rglob("*") if p.is_file()} == before
