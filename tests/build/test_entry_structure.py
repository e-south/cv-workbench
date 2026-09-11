"""Opt-in entry hierarchy keeps one linear record and theme-owned spacing."""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from cvworkbench.build.rendering import resolve_filter_paths

FILTERS = Path(__file__).resolve().parents[2] / "build/filters"
SOURCE = """::: {#education-degree .section}
### Example University

[MSc]{.entry-detail} | [2024]{.entry-date}

Advisor: A. Mentor
:::

::: {#service-mentor .section}
### Example Institute

[Mentor]{.entry-role} | [2025]{.entry-date}

Mentored three students.
:::

Ordinary paragraph.
"""


def render(source=SOURCE, *, structured=True, extra=(), target="html5"):
    args = [
        "pandoc",
        "-t",
        target,
        "-M",
        "cvw-aligned-entries=true",
        "-M",
        "cvw-concise-entries=true",
    ]
    for path in resolve_filter_paths(FILTERS):
        args.extend(["--lua-filter", str(path)])
    if structured:
        args.extend(["-M", "cvw-entry-structure=true"])
    args.extend(extra)
    return subprocess.run(args, input=source, text=True, capture_output=True, check=True).stdout


def test_shared_details_style_applies_across_record_kinds_without_touching_prose():
    tree = ET.fromstring("<root>" + render() + "</root>")
    for identity, text in [
        ("education-degree", "Advisor: A. Mentor"),
        ("service-mentor", "Mentored three students."),
    ]:
        entry = tree.find(f".//*[@id='{identity}']")
        assert "cv-entry" in entry.get("class").split()
        body = entry.find(".//*[@class='entry-details']")
        assert body is not None
        assert body.get("data-custom-style") == "Entry Details"
        assert text in "".join(body.itertext())
    assert tree.findall("p")[-1].text == "Ordinary paragraph."
    unstyled = ET.fromstring("<root>" + render(structured=False) + "</root>")
    assert not unstyled.findall(".//*[@class='entry-details']")


def test_selected_activities_use_real_lists_and_preserve_nested_teaching_ids(tmp_path):
    source = (
        """---
cvw-bulleted-entries: [service, teaching]
---
"""
        + SOURCE
        + """
:::: {.teaching-course}
### Example Course

[Teaching Fellow]{.entry-role}

::: {#teaching-first .section}
Fall 2024 | Enrollment: 30
:::

::: {#teaching-second .section}
Spring 2023 | Enrollment: 40
:::
::::
"""
    )
    tree = ET.fromstring("<root>" + render(source) + "</root>")
    for identity in ["service-mentor", "teaching-first", "teaching-second"]:
        entries = tree.findall(f".//*[@id='{identity}']")
        assert len(entries) == 1
        assert entries[0].find("ul/li") is not None
    assert tree.find(".//*[@id='education-degree']/ul") is None
    assert "".join(tree.itertext()).count("Example Course") == 1
    from zipfile import ZipFile

    target = tmp_path / "lists.docx"
    render(source, target="docx", extra=("-o", str(target)))
    with ZipFile(target) as z:
        doc = ET.fromstring(z.read("word/document.xml"))
        numbering = ET.fromstring(z.read("word/numbering.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    w = "{" + ns["w"] + "}"
    assert not doc.findall(".//w:tbl", ns)
    listed = [p for p in doc.findall(".//w:p", ns) if p.find("w:pPr/w:numPr", ns) is not None]
    visible = []
    for p in listed:
        num = p.find("w:pPr/w:numPr/w:numId", ns).get(w + "val")
        abstract = numbering.find(f"w:num[@w:numId='{num}']/w:abstractNumId", ns).get(w + "val")
        label = numbering.find(f"w:abstractNum[@w:abstractNumId='{abstract}']/w:lvl/w:lvlText", ns)
        if label.get(w + "val").strip():
            visible.append(p)
    assert len(visible) == 3
    assert any(
        "Mentor" in "".join(p.itertext()) and p.find(".//w:tab", ns) is not None for p in listed
    )


def test_unknown_bullet_kind_fails_instead_of_silently_ignoring_a_typo():
    import pytest

    with pytest.raises(subprocess.CalledProcessError) as error:
        render("---\ncvw-bulleted-entries: [educaton]\n---\n" + SOURCE)
    assert "Unknown cvw-bulleted-entries kind: educaton" in error.value.stderr


def test_bullet_configuration_requires_a_list():
    import pytest

    for value in ["service", "{service: true}"]:
        with pytest.raises(subprocess.CalledProcessError) as error:
            render("---\ncvw-bulleted-entries: " + value + "\n---\n" + SOURCE)
        assert "cvw-bulleted-entries must be a list" in error.value.stderr


def test_pdf_detail_spacing_is_shared_and_does_not_leak(tmp_path):
    import pymupdf

    source = SOURCE.replace(
        "Mentored three students.", "Mentored three students.\n\nReviewed their work."
    )
    source += "\nAnother ordinary paragraph.\n"
    gaps = []
    for tight in [False, True]:
        header = tmp_path / f"header-{tight}.tex"
        text = r"\setlength{\parskip}{8pt}"
        if tight:
            text += r"\newcommand{\cvwentrydetails}{\setlength{\parskip}{0pt}}"
        header.write_text(text)
        output = tmp_path / f"spacing-{tight}.pdf"
        render(
            source,
            target="latex",
            extra=("--pdf-engine=xelatex", "-H", str(header), "-o", str(output)),
        )
        with pymupdf.open(output) as doc:
            page = doc[0]

            def y(value, page=page):
                return page.search_for(value)[0].y0

            gaps.append(
                (
                    y("Advisor:") - y("MSc"),
                    y("Reviewed") - y("Mentored"),
                    y("Another ordinary") - y("Ordinary paragraph."),
                )
            )
    assert 7 < gaps[0][0] - gaps[1][0] < 9
    assert 7 < gaps[0][1] - gaps[1][1] < 9
    assert abs(gaps[0][2] - gaps[1][2]) < 0.1


def test_short_inline_labels_stay_together_without_missing_hyphen_glyphs(tmp_path):
    import pymupdf

    source = "\n\n".join(
        "Author " * count + r"**[\[*Co-first author\]]{.keep-together}**" for count in range(8, 16)
    )
    target = tmp_path / "labels.pdf"
    render(
        source,
        target="latex",
        extra=(
            "--pdf-engine=xelatex",
            "-V",
            "geometry:paperwidth=5in,paperheight=8in,margin=0.5in",
            "-o",
            str(target),
        ),
    )
    with pymupdf.open(target) as pdf:
        assert sum(len(page.search_for("Co-first author")) for page in pdf) == 8
    html = ET.fromstring("<root>" + render(source) + "</root>")
    assert all(
        s.get("style") == "white-space: nowrap"
        for s in html.findall(".//*[@class='keep-together']")
    )

    from zipfile import ZipFile

    target = tmp_path / "labels.docx"
    render(source, target="docx", extra=("-o", str(target)))
    with ZipFile(target) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    assert len(root.findall(".//w:noBreakHyphen", ns)) == 8
    assert sum((t.text or "").count("\u00a0") for t in root.findall(".//w:t", ns)) == 8
