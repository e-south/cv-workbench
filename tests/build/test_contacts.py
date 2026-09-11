"""Verify useful, literal contact labels and safe destinations in exported documents."""

import subprocess
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from zipfile import ZipFile

import pymupdf
import pytest
import yaml
from typer.testing import CliRunner

from cvworkbench.build.markdown import build_markdown
from cvworkbench.build.pipeline import build_documents
from cvworkbench.cli import app
from cvworkbench.variants import load_variant


class ContactHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = {}
        self.tags = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "a":
            self.current = dict(attrs).get("href")
            self.links[self.current] = ""

    def handle_endtag(self, tag):
        if tag == "a":
            self.current = None

    def handle_data(self, data):
        if self.current is not None:
            self.links[self.current] += data


@pytest.mark.parametrize("variant_id,stem", [("base", "cv"), ("cover-letter", "cover-letter")])
def test_contact_links_survive_real_exports(sample_workspace, variant_id, stem):
    person_path = Path("sot.sample/person.yaml")
    person = yaml.safe_load(person_path.read_text())
    person["email"] = "alex+work@example.com"
    person["links"] = [
        {"label": "Research", "url": "https://example.com/work?year=2026&topic=genes#results"},
        {"label": "Profile", "url": "https://example.org/alex"},
    ]
    person_path.write_text(yaml.safe_dump(person))
    before = person_path.read_bytes()
    result = build_documents(
        sot_path=Path("sot.sample"),
        config_path=Path("config/workbench.yaml"),
        variant_id=variant_id,
        formats=["md", "html", "pdf", "docx"],
    )
    expected = {
        "mailto:alex%2Bwork@example.com": "alex+work@example.com",
        person["links"][0]["url"]: "Research",
        person["links"][1]["url"]: "Profile",
    }
    html = ContactHTML()
    html.feed((result.dist_dir / f"{stem}.html").read_text())
    assert {url: html.links.get(url) for url in expected} == expected
    with pymupdf.open(result.dist_dir / f"{stem}.pdf") as pdf:
        destinations = {link["uri"] for page in pdf for link in page.get_links() if "uri" in link}
        assert set(expected) <= destinations
        text = "\n".join(page.get_text() for page in pdf)
        assert all(label in text for label in expected.values())
        assert all(url not in text for url in expected)
    with ZipFile(result.dist_dir / f"{stem}.docx") as document:
        relationships = ET.fromstring(document.read("word/_rels/document.xml.rels"))
        destinations = {
            r.get("Target") for r in relationships if r.get("Type", "").endswith("/hyperlink")
        }
        assert set(expected) <= destinations
    markdown = (result.dist_dir / f"{stem}.md").read_text()
    assert "[Research]" in markdown
    assert person_path.read_bytes() == before


def test_contact_labels_are_literal_text(sample_workspace):
    label = "Research [2026] *notes* <lab> & details"
    target = "https://example.com/a(b)?q=one&y=two#work"
    variant = load_variant(Path("config/variants/base.yaml"))
    markdown = build_markdown(
        {"person": {"name": "Example", "links": [{"label": label, "url": target}]}}, variant
    )
    rendered = subprocess.run(
        ["pandoc", "--from", "markdown+fenced_divs", "--to", "html5"],
        input=markdown,
        text=True,
        capture_output=True,
        check=True,
    )
    html = ContactHTML()
    html.feed(rendered.stdout)
    assert html.links == {target: label}
    assert not {"em", "strong", "img", "lab", "script"} & set(html.tags)


@pytest.mark.parametrize(
    "target",
    [
        "javascript:alert(1)",
        "file:///tmp/private",
        "//example.com/profile",
        "https://user:password@example.com",
        "https://example.com/\nprofile",
    ],
)
def test_invalid_profile_destination_fails_before_artifact_writes(sample_workspace, target):
    person_path = Path("sot.sample/person.yaml")
    person = yaml.safe_load(person_path.read_text())
    person["links"] = [{"label": "Profile", "url": target}]
    person_path.write_text(yaml.safe_dump(person))
    before = {str(p): p.read_bytes() for p in Path("var").rglob("*") if p.is_file()}
    result = CliRunner().invoke(app, ["build", "--variant", "base", "--format", "md", "--json"])
    assert result.exit_code == 1
    assert not result.stdout
    assert "Contact profile" in result.stderr
    assert target not in result.stderr
    assert {str(p): p.read_bytes() for p in Path("var").rglob("*") if p.is_file()} == before


def test_excluded_contacts_do_not_create_links_or_validate_destinations(sample_workspace):
    config = Path("config/variants/base.yaml")
    payload = yaml.safe_load(config.read_text())
    payload["variant"]["contact_fields"] = ["location"]
    config.write_text(yaml.safe_dump(payload))
    variant = load_variant(config)
    markdown = build_markdown(
        {
            "person": {
                "name": "Example",
                "email": "not an email",
                "phone": "private",
                "links": [{"label": "hidden", "url": "javascript:alert(1)"}],
                "location": {"city": "Example City"},
            }
        },
        variant,
    )
    assert "Example City" in markdown
    assert all(
        value not in markdown for value in ("private", "not an email", "hidden", "javascript")
    )


@pytest.mark.parametrize(
    "address",
    [
        "no-mailbox",
        "mailto:alex@example.com",
        "alex@example.com?subject=secret",
        "alex@example.com\nBcc:hidden@example.com",
    ],
)
def test_email_destination_requires_a_bare_address(sample_workspace, address):
    variant = load_variant(Path("config/variants/base.yaml"))
    with pytest.raises(ValueError, match="Contact email"):
        build_markdown({"person": {"name": "Example", "email": address}}, variant)
