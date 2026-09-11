"""Unfinished manuscripts retain explicit status without invented authorship."""

import pytest
from pydantic import ValidationError

from cvworkbench.build.markdown import build_markdown
from cvworkbench.build.resume import build_resume
from cvworkbench.inputs.sot_schema import Projects, Publication
from cvworkbench.variants import parse_variant


def test_preparation_status_survives_validation_and_exports_without_authors():
    record = {
        "id": "draft",
        "title": "A working manuscript",
        "status": "in_preparation",
        "notes": "Working title.",
        "tags": ["research"],
    }
    Publication.model_validate(record)
    source = {"publications": {"publications": [record]}}
    variant = parse_variant({"variant": {"id": "cv", "outputs": ["md"], "order": ["publications"]}})
    markdown = build_markdown(source, variant)
    assert markdown.count("## Publications") == 1
    assert "Manuscript in preparation" in markdown
    assert "Working title." in markdown and "Published" not in markdown
    exported = build_resume(source)["publications"][0]
    assert exported["status"] == "in_preparation"
    assert "authors" not in exported and "releaseDate" not in exported


@pytest.mark.parametrize("status", [None, "published"])
def test_published_and_legacy_records_require_authorship(status):
    record = {"id": "paper", "title": "A paper", "tags": ["research"]}
    if status is not None:
        record["status"] = status
    with pytest.raises(ValidationError, match="authors"):
        Publication.model_validate(record)
    record["authors"] = [{"name": "A. Author"}]
    assert Publication.model_validate(record).status == "published"


def test_unknown_status_is_rejected():
    with pytest.raises(ValidationError):
        Publication.model_validate(
            {"id": "draft", "title": "Draft", "tags": ["research"], "status": "almost_accepted"}
        )


def test_publication_venue_makes_published_label_redundant():
    variant = parse_variant({"variant": {"id": "cv", "outputs": ["md"], "order": ["publications"]}})
    record = {
        "id": "paper",
        "title": "A paper",
        "authors": [{"name": "A. Author"}],
        "status": "published",
        "venue": "Example Journal",
        "year": 2024,
    }
    source = {"publications": {"publications": [record]}}
    assert "Published" not in build_markdown(source, variant)
    record.pop("venue")
    assert "Published" in build_markdown(source, variant)


def test_migrating_all_manuscripts_does_not_require_placeholder_projects():
    assert Projects.model_validate({"projects": []}).projects == []


@pytest.mark.parametrize(
    ("details", "citation"),
    [
        (
            {
                "venue": "Example Journal",
                "year": 2024,
                "volume": "7",
                "issue": "2",
                "pages": "10–20",
            },
            "A. Author. Example Journal (2024), 7(2): 10–20",
        ),
        ({"status": "in_preparation", "year": 2026}, "A. Author. 2026. Manuscript in preparation"),
        (
            {"venue": "Example Journal", "issue": "2", "pages": "e123"},
            "A. Author. Example Journal, issue 2: e123",
        ),
    ],
)
def test_publication_metadata_uses_readable_citation_punctuation(details, citation):
    record = {"id": "paper", "title": "A paper", "authors": [{"name": "A. Author"}], **details}
    variant = parse_variant({"variant": {"id": "cv", "outputs": ["md"], "order": ["publications"]}})
    markdown = build_markdown({"publications": {"publications": [record]}}, variant)
    assert citation.replace("A. Author", "[A. Author]{.author}") in markdown
    assert " | " not in markdown
