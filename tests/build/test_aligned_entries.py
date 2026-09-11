"""Semantic date alignment preserves complete entries and linear reading order."""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

import pymupdf
import pytest
import yaml

from cvworkbench.build.markdown import build_markdown
from cvworkbench.build.pipeline import build_documents
from cvworkbench.variants import parse_variant

FILTER = Path(__file__).resolve().parents[2] / "build/filters/presentation.lua"


def test_pdf_theme_can_space_entries_without_changing_their_text(tmp_path):
    source = """::: {#education-a .section}
### First University

[MSc]{.entry-detail}
:::

::: {#education-b .section}
### Second University

[BSc]{.entry-detail}
:::
"""
    distances = []
    for gap in (0, 12):
        header = tmp_path / f"gap-{gap}.tex"
        header.write_text(r"\newcommand{\cvwentryspace}{\vspace{" + str(gap) + "pt}}")
        target = tmp_path / f"gap-{gap}.pdf"
        subprocess.run(
            [
                "pandoc",
                "--pdf-engine=xelatex",
                "--lua-filter",
                str(FILTER),
                "-M",
                "cvw-aligned-entries=true",
                "-H",
                str(header),
                "-o",
                str(target),
            ],
            input=source,
            text=True,
            capture_output=True,
            check=True,
        )
        with pymupdf.open(target) as pdf:
            first = pdf[0].search_for("First University")[0]
            second = pdf[0].search_for("Second University")[0]
            assert "MSc" in pdf[0].get_text() and "BSc" in pdf[0].get_text()
            distances.append(second.y0 - first.y0)
    assert 11 < distances[1] - distances[0] < 13


def test_aligned_role_preserves_inline_identity_and_literal_content():
    source = """::: {#role-example .role}
### [Researcher]{#role-name .entry-role} - [Example Lab]{#employer .entry-organization}

[2024]{.entry-date}

- Measured a response.
:::
"""
    rendered = subprocess.run(
        ["pandoc", "-t", "html5", "--lua-filter", str(FILTER), "-M", "cvw-aligned-entries=true"],
        input=source,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    tree = ET.fromstring("<root>" + rendered + "</root>")
    for identity in ("role-example", "role-name", "employer"):
        assert len(tree.findall(f".//*[@id='{identity}']")) == 1
    heading = tree.find(".//*[@class='entry-heading']")
    assert "Example Lab" in "".join(heading.itertext())
    assert "Researcher" not in "".join(heading.itertext())
    assert "Measured a response." in "".join(tree.itertext())


def test_education_details_spacing_is_scoped_to_the_entry(tmp_path):
    source = education_markdown({"start": "2020-09"}) + "\nAfter education.\n\nNormal paragraph.\n"
    gaps = []
    for tight in (False, True):
        header = tmp_path / f"details-{tight}.tex"
        tex = r"\setlength{\parskip}{8pt}"
        if tight:
            tex += r"\newcommand{\cvweducationdetails}{\setlength{\parskip}{0pt}}"
        header.write_text(tex)
        target = tmp_path / f"details-{tight}.pdf"
        subprocess.run(
            [
                "pandoc",
                "--pdf-engine=xelatex",
                "--lua-filter",
                str(FILTER),
                "-M",
                "cvw-aligned-entries=true",
                "-M",
                "cvw-concise-entries=true",
                "-H",
                str(header),
                "-o",
                str(target),
            ],
            input=source,
            text=True,
            capture_output=True,
            check=True,
        )
        with pymupdf.open(target) as pdf:
            page = pdf[0]
            degree = page.search_for("PhD Candidate")[0]
            advisor = page.search_for("Advisors:")[0]
            after = page.search_for("After education.")[0]
            normal = page.search_for("Normal paragraph.")[0]
            assert "cellular regulation" in page.get_text()
            gaps.append((advisor.y0 - degree.y0, normal.y0 - after.y0))
    assert 7 < gaps[0][0] - gaps[1][0] < 9
    assert abs(gaps[0][1] - gaps[1][1]) < 0.1


def education_markdown(dates):
    variant = parse_variant({"variant": {"id": "test", "outputs": ["md"], "order": ["education"]}})
    return build_markdown(
        {
            "education": {
                "education": [
                    {
                        "id": "degree",
                        "institution": "Example University",
                        "area": "Biology",
                        "study_type": "PhD Candidate",
                        "location": "Example City",
                        "advisors": ["A. Mentor"],
                        "thesis_title": "A long thesis about cellular regulation",
                        "highlights": ["Research distinction"],
                        **dates,
                    }
                ]
            }
        },
        variant,
    )


@pytest.mark.parametrize("dates", [{"start": "2020-09"}, {"end": "2019-09"}, {}])
def test_aligned_education_retains_detail_lines_and_optional_dates(dates):
    rendered = subprocess.run(
        [
            "pandoc",
            "-t",
            "html5",
            "--lua-filter",
            str(FILTER),
            "-M",
            "cvw-aligned-entries=true",
            "-M",
            "cvw-compact-entries=true",
        ],
        input=education_markdown(dates),
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    tree = ET.fromstring("<root>" + rendered + "</root>")
    entry = tree.find(".//*[@id='education-degree']")
    heading = entry.find(".//*[@class='entry-heading']")
    assert heading is not None
    heading_text = "".join(heading.itertext())
    assert "Example University" in heading_text and "Example City" in heading_text
    assert "Biology" not in heading_text
    # An end date alone does not establish that a degree was awarded.
    assert "Graduated" not in heading_text
    paragraphs = ["".join(p.itertext()) for p in entry.findall("p")]
    assert "PhD Candidate - Biology" in paragraphs
    assert "Advisors: A. Mentor" in paragraphs
    assert "Thesis: “A long thesis about cellular regulation”" in paragraphs
    assert "Research distinction" in "".join(entry.itertext())
    date_spans = entry.findall(".//*[@class='entry-date']")
    assert len(date_spans) == bool(dates)


@pytest.mark.parametrize("concise", [False, True])
def test_aligned_docx_uses_a_tab_without_layout_tables(tmp_path, concise):
    target = tmp_path / "education.docx"
    subprocess.run(
        [
            "pandoc",
            "-t",
            "docx",
            "-o",
            str(target),
            "--lua-filter",
            str(FILTER),
            "-M",
            "cvw-aligned-entries=true",
            "-M",
            f"cvw-concise-entries={str(concise).lower()}",
        ],
        input=education_markdown({"start": "2020-09"}),
        text=True,
        capture_output=True,
        check=True,
    )
    with ZipFile(target) as package:
        tree = ET.fromstring(package.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    assert not tree.findall(".//w:tbl", ns)
    heading = next(
        p
        for p in tree.findall(".//w:body/w:p", ns)
        if "Example University" in "".join(p.itertext())
    )
    assert heading.find(".//w:tab", ns) is not None
    assert heading.find("w:pPr/w:pStyle", ns).get(f"{{{ns['w']}}}val") == "EntryHeading"
    assert "Started Sept. 2020" in "".join(heading.itertext()).replace("\xa0", " ")
    detail_paragraphs = [
        p
        for p in tree.findall(".//w:body/w:p", ns)
        if any(text in "".join(p.itertext()) for text in ("PhD Candidate", "Advisors:", "Thesis:"))
    ]
    assert len(detail_paragraphs) == 3
    if concise:
        assert all(
            p.find("w:pPr/w:pStyle", ns).get(f"{{{ns['w']}}}val") == "EducationDetails"
            for p in detail_paragraphs
        )


def test_native_build_uses_packaged_alignment_and_retains_manuscript_status(sample_workspace):
    theme = sample_workspace / "build/themes/default/pandoc/common.defaults.yaml"
    theme.write_text("standalone: true\nmetadata:\n  cvw-aligned-entries: true\n")
    source = sample_workspace / "sot.sample"
    degree = {
        "id": "degree",
        "institution": "Example University",
        "area": "Cell Biology",
        "study_type": "PhD Candidate",
        "start": "2020-09",
        "location": "Example City",
        "advisors": ["A. Mentor"],
        "thesis_title": "Molecular regulation",
        "tags": ["core"],
    }
    (source / "education.yaml").write_text(yaml.safe_dump({"education": [degree]}))
    (source / "projects.yaml").write_text("projects: []\n")
    (source / "publications.yaml").write_text(
        yaml.safe_dump(
            {
                "publications": [
                    {
                        "id": "draft",
                        "title": "A working paper",
                        "status": "in_preparation",
                        "tags": ["core"],
                    }
                ]
            }
        )
    )
    variant = sample_workspace / "config/variants/base.yaml"
    data = yaml.safe_load(variant.read_text())
    data["variant"]["order"] = ["education", "publications"]
    variant.write_text(yaml.safe_dump(data))
    result = build_documents(
        sot_path=source,
        config_path=sample_workspace / "config/workbench.yaml",
        variant_id="base",
        formats=["html", "pdf", "docx", "ats"],
    )
    assert 'class="entry-heading"' in (result.dist_dir / "cv.html").read_text()
    for filename in ("cv.html", "cv.ats.txt"):
        text = (result.dist_dir / filename).read_text()
        assert "A. Mentor" in text and "Molecular regulation" in text
        assert "Manuscript in preparation" in text
    with pymupdf.open(result.dist_dir / "cv.pdf") as document:
        page = document[0]
        identity = page.search_for("Example University")[0]
        date = page.search_for("Started Sept. 2020")[0]
        assert date.x0 > identity.x1
        assert abs(date.y0 - identity.y0) < 3
        assert date.x1 < page.rect.width
        assert "Manuscript in preparation" in "\n".join(p.get_text() for p in document)
