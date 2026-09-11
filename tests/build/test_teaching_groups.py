"""Repeated course offerings share a heading without losing term-level evidence."""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from cvworkbench.build.markdown import build_markdown
from cvworkbench.variants import parse_variant


def render(records, *, exclude_tags=()):
    variant = parse_variant(
        {
            "variant": {
                "id": "cv",
                "outputs": ["md"],
                "order": ["teaching"],
                "exclude_tags": list(exclude_tags),
            }
        }
    )
    md = build_markdown({"teaching": {"teaching": records}}, variant)
    result = subprocess.run(
        ["pandoc", "-t", "html5"], input=md, text=True, capture_output=True, check=True
    )
    return ET.fromstring("<root>" + result.stdout + "</root>")


def offerings():
    return [
        {
            "id": "autumn",
            "course": "BIO 101 Biology",
            "role": "Teaching Fellow",
            "term": "Fall 2024",
            "enrollment": 39,
            "evaluation": "4.5/5",
            "tags": ["public"],
        },
        {
            "id": "spring",
            "course": "BIO 101 Biology",
            "role": "Teaching Fellow",
            "term": "Spring 2023",
            "enrollment": 45,
            "evaluation": "4.9/5",
            "summary": "Led laboratory sessions.",
            "tags": ["private"],
        },
    ]


def test_adjacent_matching_offerings_share_a_course_and_preserve_each_term():
    tree = render(offerings())
    assert len(tree.findall(".//h3")) == 1
    assert "".join(tree.itertext()).count("Teaching Fellow") == 1
    for id_, values in [
        ("autumn", ["Fall 2024", "39", "4.5/5"]),
        ("spring", ["Spring 2023", "45", "4.9/5", "Led laboratory sessions."]),
    ]:
        text = "".join(tree.find(f".//*[@id='teaching-{id_}']").itertext())
        assert all(value in text for value in values)


def test_grouping_follows_selection_and_keeps_distinct_roles_separate():
    records = offerings()
    selected = render(records, exclude_tags=["private"])
    assert selected.find(".//*[@id='teaching-spring']") is None
    assert "45" not in "".join(selected.itertext())
    records[1]["role"] = "Instructor"
    assert len(render(records).findall(".//h3")) == 2


def test_grouping_does_not_reorder_nonadjacent_courses():
    records = offerings()
    records.insert(1, {"id": "other", "course": "BIO 202 Genetics", "role": "Teaching Fellow"})
    tree = render(records)
    assert [x.text for x in tree.findall(".//h3")] == [
        "BIO 101 Biology",
        "BIO 202 Genetics",
        "BIO 101 Biology",
    ]


def test_structural_course_group_survives_the_tag_filter():
    records = offerings()
    records[1]["tags"] = ["public"]
    variant = parse_variant(
        {
            "variant": {
                "id": "cv",
                "outputs": ["md"],
                "order": ["teaching"],
                "include_tags": ["public"],
            }
        }
    )
    markdown = build_markdown({"teaching": {"teaching": records}}, variant)
    filters = Path(__file__).resolve().parents[2] / "build/filters"
    result = subprocess.run(
        [
            "pandoc",
            "-t",
            "html5",
            "--lua-filter",
            str(filters / "select.lua"),
            "--lua-filter",
            str(filters / "presentation.lua"),
            "-M",
            "include_tags=public",
            "-M",
            "cvw-aligned-entries=true",
            "-M",
            "cvw-concise-entries=true",
        ],
        input=markdown,
        text=True,
        capture_output=True,
        check=True,
    )
    tree = ET.fromstring("<root>" + result.stdout + "</root>")
    assert "Teaching Fellow, BIO 101 Biology" in "".join(tree.itertext())
    for id_ in ("autumn", "spring"):
        assert tree.find(f".//*[@id='teaching-{id_}']") is not None


def test_inline_teaching_keeps_terms_bound_to_scores_and_falls_back_for_narrative(tmp_path):
    from cvworkbench.build.rendering import resolve_filter_paths

    records = offerings()
    records[1].pop("summary")
    variant = parse_variant({"variant": {"id": "cv", "outputs": ["md"], "order": ["teaching"]}})
    filters = Path(__file__).resolve().parents[2] / "build/filters"

    def output():
        md = build_markdown({"teaching": {"teaching": records}}, variant)
        args = [
            "pandoc",
            "-t",
            "html5",
            "-M",
            "cvw-inline-teaching=true",
            "-M",
            "cvw-aligned-entries=true",
            "-M",
            "cvw-concise-entries=true",
            "-M",
            "cvw-entry-structure=true",
        ]
        for path in resolve_filter_paths(filters):
            args.extend(["--lua-filter", str(path)])
        result = subprocess.run(args, input=md, text=True, capture_output=True, check=True)
        return ET.fromstring("<root>" + result.stdout + "</root>")

    tree = output()
    assert len(tree.findall(".//p")) == 2
    for identity, expected in [
        ("autumn", "Fall 2024 | 39 students | evaluation 4.5/5"),
        ("spring", "Spring 2023 | 45 students | evaluation 4.9/5"),
    ]:
        span = tree.find(f".//span[@id='teaching-{identity}']")
        assert span is not None
        assert " ".join("".join(span.itertext()).split()) == expected
    records[1]["summary"] = "Led laboratory sessions."
    tree = output()
    assert tree.find(".//span[@id='teaching-spring']") is None
    assert "Led laboratory sessions." in "".join(tree.itertext())
