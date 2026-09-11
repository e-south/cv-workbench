"""Presentation references retain source identity and reject information loss."""

import subprocess
from pathlib import Path

import pytest
import yaml

from cvworkbench.build.markdown import build_markdown
from cvworkbench.build.rendering import resolve_filter_paths
from cvworkbench.variants import parse_variant


def document(rules):
    source = {
        "experience": {
            "roles": [{"id": "lab", "company": "Example Lab", "title": "Researcher", "start": 2020}]
        },
        "service": {
            "service": [
                {
                    "id": "mentor",
                    "role": "Mentor",
                    "organization": "Example Lab",
                    "start": 2022,
                    "summary": "Supervised three students.",
                },
                {
                    "id": "team",
                    "role": "Team Supervisor",
                    "organization": "Example Lab",
                    "summary": "Five students built an image-analysis pipeline.",
                },
            ]
        },
        "honors": {
            "honors": [
                {"id": "award", "title": "Research Award", "issuer": "Foundation", "year": 2021}
            ]
        },
    }
    variant = parse_variant(
        {
            "variant": {
                "id": "base",
                "outputs": ["html"],
                "order": ["experience", "service", "honors"],
            }
        }
    )
    metadata = {
        "cvw-aligned-entries": True,
        "cvw-concise-entries": True,
        "cvw-entry-structure": True,
        "cvw-entry-layout": rules,
    }
    return "---\n" + yaml.safe_dump(metadata) + "---\n" + build_markdown(source, variant)


def render(source, output):
    args = ["pandoc", "--pdf-engine=xelatex", "-o", str(output)]
    for path in resolve_filter_paths(Path(__file__).resolve().parents[2] / "build/filters"):
        args.extend(["--lua-filter", str(path)])
    return subprocess.run(args, input=source, text=True, capture_output=True, check=True)


def test_groups_and_attachments_preserve_each_record_and_unknown_dates(tmp_path):
    source = document(
        [
            {"sources": ["honor-award"], "target": "role-lab", "placement": "details"},
            {
                "sources": ["service-mentor", "service-team"],
                "target": "service-leadership",
                "placement": "section",
                "label": "Research mentoring",
            },
        ]
    )
    path = tmp_path / "out.html"
    render(source, path)
    html = path.read_text()
    assert html.index("Research Award") < html.index("Service &amp; Leadership")
    assert "Research mentoring" in html
    for identity in ("honor-award", "service-mentor", "service-team"):
        assert html.count(f'id="{identity}"') == 1
    assert "Supervised three students." in html and "Five students built" in html
    assert html.count("2022") == 1
    assert "Honors &amp; Awards" not in html  # no empty section after relocation


@pytest.mark.parametrize(
    "rules",
    [
        [{"sources": ["service-missing"], "target": "role-lab", "placement": "details"}],
        [{"sources": ["service-mentor"], "target": "missing", "placement": "details"}],
        [
            {
                "sources": ["service-mentor", "service-mentor"],
                "target": "role-lab",
                "placement": "details",
            }
        ],
        [{"sources": ["service-mentor"], "target": "service-mentor", "placement": "details"}],
    ],
)
def test_projection_rejects_missing_duplicate_or_self_consumed_records(tmp_path, rules):
    with pytest.raises(subprocess.CalledProcessError) as exc:
        render(document(rules), tmp_path / "out.html")
    assert "cvw-entry-layout" in exc.value.stderr


def test_variant_projection_is_retained_and_validated():
    rules = [{"sources": ["honor-award"], "target": "role-lab", "placement": "details"}]
    variant = parse_variant(
        {"variant": {"id": "cv", "outputs": ["pdf"], "render": {"entry_layout": rules}}}
    )
    assert variant.render_entry_layout == rules
    with pytest.raises(ValueError, match="entry_layout"):
        parse_variant(
            {"variant": {"id": "cv", "outputs": ["pdf"], "render": {"entry_layout": "invalid"}}}
        )


def test_explicit_attachment_fields_keep_scope_and_date_without_repeating_role(tmp_path):
    source = document(
        [
            {
                "sources": ["service-mentor"],
                "target": "role-lab",
                "placement": "details",
                "fields": ["summary", "date"],
            }
        ]
    )
    output = tmp_path / "out.html"
    render(source, output)
    html = output.read_text()
    assert "Supervised three students." in html and "2022" in html
    assert "Mentor," not in html
    assert html.count('id="service-mentor"') == 1


def test_requested_fields_must_exist_on_each_source(tmp_path):
    source = document(
        [
            {
                "sources": ["service-team"],
                "target": "role-lab",
                "placement": "details",
                "fields": ["issuer"],
            }
        ]
    )
    with pytest.raises(subprocess.CalledProcessError) as exc:
        render(source, tmp_path / "out.html")
    assert "cvw-entry-layout" in exc.value.stderr


def publications_source(
    *, second_author="A. Scientist", second_year=2026, second_status="in_preparation"
):
    source = {
        "publications": {
            "publications": [
                {
                    "id": "one",
                    "title": "First complete title",
                    "authors": [{"name": "A. Scientist", "roles": ["self"]}],
                    "year": 2026,
                    "status": "in_preparation",
                    "url": "https://example.org/one",
                },
                {
                    "id": "two",
                    "title": "Second complete title",
                    "authors": [{"name": second_author, "roles": ["self"]}],
                    "year": second_year,
                    "status": second_status,
                },
            ]
        }
    }
    variant = parse_variant({"variant": {"id": "base", "outputs": ["html"]}})
    metadata = {
        "cvw-entry-layout": [
            {
                "sources": ["publication-one", "publication-two"],
                "target": "publications",
                "placement": "shared_citation",
            }
        ]
    }
    return "---\n" + yaml.safe_dump(metadata) + "---\n" + build_markdown(source, variant)


def test_shared_citation_retains_titles_identity_and_link(tmp_path):
    path = tmp_path / "out.html"
    render(publications_source(), path)
    html = path.read_text()
    assert html.count("Manuscripts in preparation") == 1
    assert html.count("A. Scientist") == 1
    assert "First complete title" in html and "Second complete title" in html
    assert 'href="https://example.org/one"' in html
    assert html.count('id="publication-one"') == html.count('id="publication-two"') == 1


@pytest.mark.parametrize(
    "kwargs",
    [{"second_author": "B. Scientist"}, {"second_year": 2025}, {"second_status": "published"}],
)
def test_shared_citation_rejects_different_authorship_date_or_status(tmp_path, kwargs):
    with pytest.raises(subprocess.CalledProcessError) as exc:
        render(publications_source(**kwargs), tmp_path / "out.html")
    assert "cvw-entry-layout" in exc.value.stderr


@pytest.mark.parametrize("field", ["authors", "year"])
def test_shared_citation_requires_known_authors_and_year(tmp_path, field):
    source = publications_source()
    if field == "authors":
        source = source.replace("[A. Scientist]{.author .role-self}. ", "")
    else:
        source = source.replace("2026. ", "")
    # Strip the builder's completeness assertion too: incomplete records cannot opt in.
    source = source.replace(" .publication-citation-complete", "")
    with pytest.raises(subprocess.CalledProcessError) as exc:
        render(source, tmp_path / "out.html")
    assert "cvw-entry-layout" in exc.value.stderr


@pytest.mark.parametrize("extension", ["pdf", "docx", "txt"])
def test_compact_records_survive_native_writers(tmp_path, extension):
    from xml.etree import ElementTree as ET
    from zipfile import ZipFile

    import pymupdf

    source = document(
        [
            {"sources": ["honor-award"], "target": "role-lab", "placement": "details"},
            {
                "sources": ["service-mentor", "service-team"],
                "target": "service-leadership",
                "placement": "section",
                "fields": ["summary", "date"],
            },
        ]
    )
    path = tmp_path / f"output.{extension}"
    render(source, path)
    if extension == "pdf":
        with pymupdf.open(path) as pdf:
            text = " ".join(page.get_text() for page in pdf)
    elif extension == "docx":
        with ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            assert not root.findall(".//w:tbl", ns)
            text = " ".join(node.text or "" for node in root.findall(".//w:t", ns))
    else:
        text = path.read_text()
    normalized = " ".join(text.split())
    assert "Supervised three students." in normalized and "Five students built" in normalized
    assert normalized.count("2022") == 1
    assert normalized.index("Research Award") < normalized.index("Service & Leadership")


@pytest.mark.parametrize("value", [None, {}, [], ["date", "date"], ["missing"], [3]])
def test_variant_fields_reject_invalid_values(value):
    rule = {
        "sources": ["honor-award"],
        "target": "role-lab",
        "placement": "details",
        "fields": value,
    }
    with pytest.raises(ValueError, match="entry_layout"):
        parse_variant(
            {"variant": {"id": "base", "outputs": ["html"], "render": {"entry_layout": [rule]}}}
        )


def test_unknown_source_structure_is_not_silently_discarded(tmp_path):
    source = document([{"sources": ["service-team"], "target": "role-lab", "placement": "details"}])
    source = source.replace(
        "Five students built an image-analysis pipeline.",
        "Five students built an image-analysis pipeline.\n\n- Extra evidence",
    )
    with pytest.raises(subprocess.CalledProcessError) as exc:
        render(source, tmp_path / "out.html")
    assert "unsupported record body" in exc.value.stderr


def test_native_build_records_layout_and_preserves_source_and_review_identity(sample_workspace):
    import hashlib
    import json

    from cvworkbench.build.pipeline import build_documents
    from cvworkbench.ops.review.importing import import_docx_review
    from cvworkbench.ops.review.packs import build_review_pack

    config = Path("config/workbench.yaml")
    variant_path = Path("config/variants/base.yaml")
    variant = yaml.safe_load(variant_path.read_text())
    rules = [
        {
            "sources": ["honor-outstanding-student"],
            "target": "role-acme-platform",
            "placement": "details",
        },
        {
            "sources": ["service-reading-group"],
            "target": "service-leadership",
            "placement": "section",
            "label": 'Mentoring: "research" & practice',
            "fields": ["summary", "date"],
        },
    ]
    variant["variant"]["render"] = {"entry_layout": rules}
    variant_path.write_text(yaml.safe_dump(variant))
    Path("sot.sample/service.yaml").write_text(
        yaml.safe_dump(
            {
                "service": [
                    {
                        "id": "reading-group",
                        "organization": "Example Institute",
                        "role": "Mentor",
                        "start": 2022,
                        "summary": "Supervised three researchers.",
                        "tags": ["leadership"],
                    }
                ]
            }
        )
    )
    source_hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in Path("sot.sample").glob("*.yaml")
    }
    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=config,
        variant_id="base",
        formats=["md", "html", "pdf", "docx", "ats"],
    )
    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    assert manifest["variant"]["entry_layout"] == rules
    canonical = (result.run_dir / "canonical.md").read_text()
    assert canonical.index("Outstanding Student Award") > canonical.index("## Honors")
    assert "service-reading-group" in canonical
    html = (result.dist_dir / "cv.html").read_text()
    from html import unescape

    assert 'Mentoring: "research" & practice' in unescape(html)
    assert html.index("Outstanding Student Award") < html.index("Rocket Data")
    pack = build_review_pack(config_path=config, variant_id="base", run=str(result.run_dir))
    imported = import_docx_review(
        docx_path=pack.docx_path, config_path=config, run=None, variant_id="base", project_dir=None
    )
    assert imported.apply_status == "review_diff_only"
    assert source_hashes == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in Path("sot.sample").glob("*.yaml")
    }


def test_section_group_stays_at_first_source_position(tmp_path):
    source = document(
        [
            {
                "sources": ["service-mentor"],
                "target": "service-leadership",
                "placement": "section",
                "label": "Grouped mentoring",
            }
        ]
    )
    path = tmp_path / "out.html"
    render(source, path)
    html = path.read_text()
    assert html.index("Grouped mentoring") < html.index("Team Supervisor")


def test_requested_projection_cannot_silently_skip_a_missing_filter(tmp_path):
    from cvworkbench.build.rendering import RenderError, render_document

    source = tmp_path / "source.md"
    source.write_text("## Experience\n\nPrior source.\n")
    output = tmp_path / "cv.html"
    output.write_text("Prior valid artifact")
    variant = parse_variant(
        {
            "variant": {
                "id": "cv",
                "outputs": ["html"],
                "render": {
                    "entry_layout": [
                        {"sources": ["honor-award"], "target": "role-lab", "placement": "details"}
                    ]
                },
            }
        }
    )
    with pytest.raises(RenderError, match="entry_projection.lua"):
        render_document(source, output, variant, tmp_path, "html", None, filter_paths=[])
    assert output.read_text() == "Prior valid artifact"


def test_explicit_null_label_fails_variant_validation():
    with pytest.raises(ValueError, match="entry_layout"):
        parse_variant(
            {
                "variant": {
                    "id": "cv",
                    "outputs": ["html"],
                    "render": {
                        "entry_layout": [
                            {
                                "sources": ["honor-award"],
                                "target": "honors-awards",
                                "placement": "section",
                                "label": None,
                            }
                        ]
                    },
                }
            }
        )
