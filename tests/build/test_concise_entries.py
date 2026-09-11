"""Concise presentation retains record semantics and ordinary reading order."""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

import pymupdf
import pytest
import yaml
from pydantic import ValidationError

from cvworkbench.build.markdown import build_markdown
from cvworkbench.build.pipeline import build_documents
from cvworkbench.inputs.sot_schema import ConferenceEntry
from cvworkbench.variants import parse_variant


def test_known_conference_does_not_require_an_invented_presentation_title():
    record = {
        "id": "meeting",
        "event": "Example Conference",
        "year": 2024,
        "presentation_type": "Poster",
        "tags": ["research"],
    }
    assert ConferenceEntry.model_validate(record).title is None
    variant = parse_variant({"variant": {"id": "cv", "outputs": ["md"], "order": ["conferences"]}})
    markdown = build_markdown({"conferences": {"conferences": [record]}}, variant)
    plain = subprocess.run(
        ["pandoc", "-t", "plain"], input=markdown, text=True, capture_output=True, check=True
    ).stdout
    assert plain.count("Example Conference") == 1
    assert "Poster | 2024" in plain
    with pytest.raises(ValidationError):
        ConferenceEntry.model_validate({**record, "event": ""})
    with pytest.raises(ValidationError):
        ConferenceEntry.model_validate({**record, "title": ""})


FILTER = Path(__file__).resolve().parents[2] / "build/filters/presentation.lua"


def render_entries(source, *, concise=True):
    variant = parse_variant({"variant": {"id": "cv", "outputs": ["md"], "order": list(source)}})
    markdown = build_markdown(source, variant)
    result = subprocess.run(
        [
            "pandoc",
            "-t",
            "html5",
            "--lua-filter",
            str(FILTER),
            "-M",
            "cvw-aligned-entries=true",
            "-M",
            f"cvw-concise-entries={str(concise).lower()}",
        ],
        input=markdown,
        text=True,
        capture_output=True,
        check=True,
    )
    return ET.fromstring("<root>" + result.stdout + "</root>")


@pytest.mark.parametrize("dates", [{"start": 2024}, {}])
def test_concise_service_keeps_role_organization_and_date_together(dates):
    source = {
        "service": {
            "service": [
                {
                    "id": "mentor",
                    "role": "Mentor",
                    "organization": "Example University",
                    "summary": "Supervised three students.",
                    **dates,
                }
            ]
        }
    }
    tree = render_entries(source)
    entry = tree.find(".//*[@id='service-mentor']")
    heading = entry.find(".//*[@class='entry-heading']")
    assert "Mentor, Example University" in "".join(heading.itertext())
    assert ["".join(p.itertext()) for p in entry.findall("p")] == ["Supervised three students."]
    assert len(entry.findall(".//*[@class='entry-date']")) == bool(dates)
    original = render_entries(source, concise=False)
    assert "Mentor" not in "".join(original.find(".//*[@class='entry-heading']").itertext())


def test_concise_award_retains_issuer_and_substantive_reason():
    source = {
        "honors": {
            "honors": [
                {
                    "id": "award",
                    "title": "Student Award",
                    "issuer": "Example Foundation",
                    "year": 2024,
                    "summary": "Top of the graduating class.",
                }
            ]
        }
    }
    entry = render_entries(source).find(".//*[@id='honor-award']")
    assert "Student Award, Example Foundation" in "".join(
        entry.find(".//*[@class='entry-heading']").itertext()
    )
    assert ["".join(p.itertext()) for p in entry.findall("p")] == ["Top of the graduating class."]


def test_concise_education_keeps_advisors_and_thesis_separate_from_short_highlights():
    source = {
        "education": {
            "education": [
                {
                    "id": "degree",
                    "institution": "Example University",
                    "study_type": "MSc",
                    "area": "Biology",
                    "end": 2024,
                    "advisors": ["A. Mentor"],
                    "thesis_title": "Cellular regulation",
                    "highlights": ["GPA: 3.8", "Distinction"],
                }
            ]
        }
    }
    entry = render_entries(source).find(".//*[@id='education-degree']")
    details = entry.find(".//*[@class='education-details']")
    assert details.attrib["data-custom-style"] == "Education Details"
    assert ["".join(p.itertext()) for p in details.findall("p")] == [
        "MSc - Biology; GPA: 3.8; Distinction",
        "Advisors: A. Mentor",
        "Thesis: “Cellular regulation”",
    ]
    assert not entry.findall("ul")
    assert len(render_entries(source, concise=False).findall(".//li")) == 2


def test_concise_manuscript_retains_status_and_working_title_on_one_line():
    source = {
        "publications": {
            "publications": [
                {
                    "id": "draft",
                    "title": "A working paper",
                    "status": "in_preparation",
                    "notes": "Working title.",
                }
            ]
        }
    }
    entry = render_entries(source).find(".//*[@id='publication-draft']")
    assert ["".join(p.itertext()) for p in entry.findall("p")] == [
        "Manuscript in preparation; Working title."
    ]
    original = render_entries(source, concise=False).find(".//*[@id='publication-draft']")
    assert len(original.findall("p")) == 2


def test_concise_published_note_stays_with_its_citation():
    source = {
        "publications": {
            "publications": [
                {
                    "id": "paper",
                    "title": "A published paper",
                    "status": "published",
                    "authors": [{"name": "A. Author"}],
                    "venue": "Example Journal",
                    "notes": "*Equal contribution.",
                }
            ]
        }
    }
    entry = render_entries(source).find(".//*[@id='publication-paper']")
    paragraphs = entry.findall("p")
    assert len(paragraphs) == 1
    assert "Equal contribution." in "".join(paragraphs[0].itertext())
    text = "".join(paragraphs[0].itertext())
    assert (
        text.index("A. Author") < text.index("Equal contribution.") < text.index("Example Journal")
    )


@pytest.mark.parametrize("title", [None, "A known poster title"])
def test_concise_conference_activity_shares_the_event_heading(title):
    record = {
        "id": "meeting",
        "event": "Example Conference",
        "year": 2024,
        "presentation_type": "Poster",
    }
    if title:
        record["title"] = title
    source = {"conferences": {"conferences": [record]}}
    entry = render_entries(source).find(".//*[@id='conference-meeting']")
    assert "Poster, Example Conference" in "".join(
        entry.find(".//*[@class='entry-heading']").itertext()
    )
    assert ["".join(p.itertext()) for p in entry.findall("p")] == ([title] if title else [])


def test_concise_teaching_groups_role_and_course_above_term_evidence():
    source = {
        "teaching": {
            "teaching": [
                {
                    "id": "fall",
                    "course": "BIO 101",
                    "role": "Teaching Fellow",
                    "term": "Fall 2024",
                    "enrollment": 39,
                },
                {
                    "id": "spring",
                    "course": "BIO 101",
                    "role": "Teaching Fellow",
                    "term": "Spring 2023",
                    "enrollment": 45,
                },
            ]
        }
    }
    tree = render_entries(source)
    heading = tree.find(".//*[@class='entry-heading']")
    assert heading is not None
    assert "Teaching Fellow, BIO 101" in "".join(heading.itertext())
    for id_, term in [("fall", "Fall 2024"), ("spring", "Spring 2023")]:
        assert term in "".join(tree.find(f".//*[@id='teaching-{id_}']").itertext())


@pytest.mark.parametrize(
    "metadata",
    [
        "[Mentor]{.entry-role} | [2024]{.entry-date} | Unknown metadata",
        "[Mentor]{.entry-role} | [Chair]{.entry-role} | [2024]{.entry-date}",
        "[Foundation]{.entry-issuer} | [University]{.entry-issuer} | [2024]{.entry-date}",
    ],
)
def test_ambiguous_metadata_is_preserved_without_restructuring(metadata):
    source = f"::: {{#service-example .section}}\n### Example University\n\n{metadata}\n\nRetain this.\n:::\n"
    result = subprocess.run(
        [
            "pandoc",
            "-t",
            "html5",
            "--lua-filter",
            str(FILTER),
            "-M",
            "cvw-aligned-entries=true",
            "-M",
            "cvw-concise-entries=true",
        ],
        input=source,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    tree = ET.fromstring("<root>" + result + "</root>")
    assert tree.find(".//h3") is not None
    assert tree.find(".//*[@class='entry-heading']") is None
    assert "Retain this." in "".join(tree.itertext())
    for word in ("Unknown", "Chair", "Foundation"):
        if word in metadata:
            assert word in "".join(tree.itertext())


def test_nested_education_highlights_remain_a_list():
    source = """::: {#education-example .section}
### Example University

[MSc]{.entry-detail} | [2024]{.entry-date}

- Placement
  - A nested contribution
:::
"""
    result = subprocess.run(
        [
            "pandoc",
            "-t",
            "html5",
            "--lua-filter",
            str(FILTER),
            "-M",
            "cvw-aligned-entries=true",
            "-M",
            "cvw-concise-entries=true",
        ],
        input=source,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    tree = ET.fromstring("<root>" + result + "</root>")
    assert tree.find(".//ul/li/ul/li") is not None
    assert "A nested contribution" in "".join(tree.itertext())


def test_installed_concise_filter_preserves_native_export_fields(sample_workspace):
    source = sample_workspace / "sot.sample"
    records = {
        "service": [
            {
                "id": "mentor",
                "organization": "Example University",
                "role": "Mentor",
                "start": 2024,
                "end": 2024,
                "summary": "Supervised three students.",
                "tags": ["core"],
            }
        ],
        "honors": [
            {
                "id": "award",
                "title": "Research Fellowship",
                "issuer": "Example Foundation",
                "year": 2024,
                "summary": "Supported a research placement.",
                "tags": ["core"],
            }
        ],
        "conferences": [
            {
                "id": "meeting",
                "event": "Example Conference",
                "year": 2024,
                "presentation_type": "Poster",
                "tags": ["core"],
            }
        ],
        "publications": [
            {
                "id": "draft",
                "title": "A working paper",
                "status": "in_preparation",
                "notes": "Working title.",
                "tags": ["core"],
            }
        ],
    }
    for name, entries in records.items():
        (source / f"{name}.yaml").write_text(yaml.safe_dump({name: entries}))
    theme = sample_workspace / "build/themes/default/pandoc/common.defaults.yaml"
    theme.write_text(
        "standalone: true\nmetadata:\n  cvw-aligned-entries: true\n  cvw-concise-entries: true\n"
    )
    variant = sample_workspace / "config/variants/base.yaml"
    data = yaml.safe_load(variant.read_text())
    data["variant"]["order"] = list(records)
    variant.write_text(yaml.safe_dump(data))
    result = build_documents(
        sot_path=source,
        config_path=sample_workspace / "config/workbench.yaml",
        variant_id="base",
        formats=["html", "pdf", "docx", "ats"],
    )
    html = (result.dist_dir / "cv.html").read_text()
    assert 'class="entry-role"' in html
    with ZipFile(result.dist_dir / "cv.docx") as package:
        tree = ET.fromstring(package.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = [
        "".join(t.text or "" for t in p.findall(".//w:t", ns))
        for p in tree.findall(".//w:body/w:p", ns)
    ]
    assert "Mentor, Example University2024" in paragraphs
    assert "Manuscript in preparation; Working title." in paragraphs
    assert not tree.findall(".//w:tbl", ns)
    assert tree.find(".//w:tab", ns) is not None
    with pymupdf.open(result.dist_dir / "cv.pdf") as document:
        text = "\n".join(p.get_text() for p in document)
        date = document[0].search_for("2024")[0]
        label = document[0].search_for("Mentor, Example University")[0]
        assert date.x0 > label.x1
        assert abs(date.y0 - label.y0) < 3
        assert "Manuscript in preparation; Working title." in text
    ats = (result.dist_dir / "cv.ats.txt").read_text()
    for value in (
        "Example University",
        "Example Foundation",
        "Example Conference",
        "Poster",
        "Supervised three students.",
        "Manuscript in preparation",
        "Working title.",
    ):
        assert value in ats
