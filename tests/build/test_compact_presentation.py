"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_compact_presentation.py

Verifies optional presentation preserves selected content and document identities.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from cvworkbench.build.markdown import build_markdown
from cvworkbench.build.pipeline import build_documents
from cvworkbench.variants import load_variants_from_config, parse_variant

FILTER = Path(__file__).resolve().parents[2] / "build/filters/presentation.lua"
SOURCE = """::: {#education-example .section .tag-education}
### Example University {#explicit-heading .entry-heading data-source="degree"}

MRes | 2025 | [Research](https://example.org/work)

An independent narrative paragraph.

[Self author]{#self-author .author .role-self data-source="author"}
:::
"""


@pytest.mark.parametrize("compact", [False, True])
def test_compact_keeps_identity_links_and_narrative(compact):
    args = ["pandoc", "-f", "markdown+fenced_divs", "-t", "json", "--lua-filter", str(FILTER)]
    if compact:
        args += ["-M", "cvw-compact-entries=true"]
    result = subprocess.run(args, input=SOURCE, text=True, capture_output=True, check=True)
    div = json.loads(result.stdout)["blocks"][0]
    assert div["c"][0][0] == "education-example"
    blocks = div["c"][1]
    assert [block["t"] for block in blocks] == (
        ["Para", "Para", "Para"] if compact else ["Header", "Para", "Para", "Para"]
    )
    assert "https://example.org/work" in result.stdout
    assert "independent" in result.stdout
    assert "University" in result.stdout
    heading = blocks[0]["c"][0] if compact else blocks[0]
    heading_attr = heading["c"][0] if compact else heading["c"][1]
    assert heading_attr == ["explicit-heading", ["entry-heading"], [["data-source", "degree"]]]
    author = blocks[-1]["c"][0]
    assert author["t"] == "Span"
    assert author["c"][0] == ["self-author", ["author", "role-self"], [["data-source", "author"]]]


def test_section_labels_change_headings_not_selection():
    variant = parse_variant(
        {
            "variant": {
                "id": "example",
                "outputs": ["md"],
                "order": ["experience"],
                "section_titles": {"experience": "Research & Development"},
            }
        }
    )
    source = {
        "experience": {
            "roles": [
                {
                    "id": "role-one",
                    "title": "Scientist",
                    "company": "Example",
                    "start": 2024,
                    "bullets": [{"id": "one", "text": "Measured response.", "tags": []}],
                }
            ]
        }
    }
    rendered = build_markdown(source, variant)
    assert "## Research \\& Development" in rendered
    assert "#role-role-one" in rendered and "Measured response." in rendered


def test_section_labels_are_recorded_in_catalog_and_manifest(sample_workspace):
    config = sample_workspace / "config/workbench.yaml"
    path = config.parent / "variants/base.yaml"
    data = yaml.safe_load(path.read_text())
    labels = {"skills": "Technical Skills"}
    data["variant"]["section_titles"] = labels
    path.write_text(yaml.safe_dump(data))
    catalog = load_variants_from_config(config)
    assert next(item for item in catalog if item["id"] == "base")["section_titles"] == labels
    result = build_documents(
        sot_path=sample_workspace / "sot.sample",
        config_path=config,
        variant_id="base",
        formats=["md"],
    )
    manifest = json.loads((result.dist_dir / "manifest.json").read_text())
    assert manifest["variant"]["section_titles"] == labels


@pytest.mark.parametrize(
    "titles", [{"unknown": "Title"}, {"skills": ""}, {"skills": "Title\nInjected"}, ["skills"]]
)
def test_invalid_section_labels_fail_before_build(titles):
    with pytest.raises(ValueError, match="section_titles"):
        parse_variant({"variant": {"id": "example", "outputs": ["md"], "section_titles": titles}})


@pytest.mark.parametrize(
    "dates,expected",
    [
        ({"end": 2019}, "2019"),
        ({"start": 2022, "end": 2022}, "2022"),
        ({"start": 2020}, "2020 — Present"),
    ],
)
def test_entry_dates_retain_completion_and_single_year(dates, expected):
    variant = parse_variant(
        {"variant": {"id": "example", "outputs": ["md"], "order": ["education"]}}
    )
    rendered = build_markdown(
        {
            "education": {
                "education": [
                    {"id": "degree", "institution": "Example", "area": "Biology", **dates}
                ]
            }
        },
        variant,
    )
    assert f"Biology | {expected}" in rendered
    assert "2022 — 2022" not in rendered


def test_compact_education_retains_highlight_text():
    source = SOURCE.replace("An independent narrative paragraph.", "- Distinction.\n- Award.")
    result = subprocess.run(
        [
            "pandoc",
            "-f",
            "markdown+fenced_divs",
            "-t",
            "json",
            "--lua-filter",
            str(FILTER),
            "-M",
            "cvw-compact-entries=true",
        ],
        input=source,
        text=True,
        capture_output=True,
        check=True,
    )
    blocks = json.loads(result.stdout)["blocks"][0]["c"][1]
    assert len(blocks) == 2 and blocks[0]["t"] == "Para"
    assert "Distinction." in result.stdout and "Award." in result.stdout


def test_publication_title_is_a_link_with_literal_label():
    variant = parse_variant(
        {"variant": {"id": "example", "outputs": ["md"], "order": ["publications"]}}
    )
    rendered = build_markdown(
        {
            "publications": {
                "publications": [
                    {
                        "id": "paper",
                        "title": "A [real] paper",
                        "url": "https://example.org/paper",
                        "authors": [{"name": "A. Author"}],
                    }
                ]
            }
        },
        variant,
    )
    assert r"[A \[real\] paper](<https://example.org/paper>)" in rendered


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/private.pdf",
        "javascript:alert(1)",
        "https://user:secret@example.org",
        "https://example.org/a b",
    ],
)
def test_publication_url_rejects_unsafe_destinations(url):
    variant = parse_variant(
        {"variant": {"id": "example", "outputs": ["md"], "order": ["publications"]}}
    )
    with pytest.raises(ValueError, match="Publication URL"):
        build_markdown(
            {"publications": {"publications": [{"title": "Paper", "url": url}]}}, variant
        )


def test_contact_rows_keep_each_link_and_plain_location():
    source = "# Example\n\n[Email](mailto:a@example.org) | Example City | [Site](https://example.org) | [Code](https://example.org/code) | [Writing](https://example.org/writing)\n"
    result = subprocess.run(
        [
            "pandoc",
            "-f",
            "markdown",
            "-t",
            "json",
            "--lua-filter",
            str(FILTER),
            "-M",
            "cvw-contact-rows=true",
        ],
        input=source,
        text=True,
        capture_output=True,
        check=True,
    )
    block = json.loads(result.stdout)["blocks"][1]
    assert block["t"] == "Div" and "contact-block" in block["c"][0][1]
    assert len(block["c"][1]) == 2

    def link_count(node):
        if isinstance(node, dict):
            return (node.get("t") == "Link") + sum(link_count(v) for v in node.values())
        if isinstance(node, list):
            return sum(link_count(v) for v in node)
        return 0

    assert link_count(block) == 4
    assert "City" in result.stdout
