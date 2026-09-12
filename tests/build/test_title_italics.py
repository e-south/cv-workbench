import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from cvworkbench.build.markdown import build_markdown
from cvworkbench.inputs.sot_schema import Publication
from cvworkbench.variants import load_variant


def publication(**changes):
    return {
        "id": "optics-study",
        "title": "Wave * patterns in Model alpha",
        "title_italics": ["Model alpha"],
        "authors": [{"name": "A. Example"}],
        "tags": ["research"],
        **changes,
    }


@pytest.mark.parametrize("url", [None, "https://example.org/paper"])
def test_title_italics_preserve_plain_citation_and_optional_link(url, sample_workspace):
    item = publication(**({"url": url} if url else {}))
    parsed = Publication.model_validate(item)
    assert parsed.title == "Wave * patterns in Model alpha"
    variant = replace(
        load_variant(Path("config/variants/base.yaml")),
        order=["publications"],
        include_tags=[],
        exclude_tags=[],
    )
    markdown = build_markdown({"publications": {"publications": [item]}}, variant)
    ast = json.loads(
        subprocess.check_output(["pandoc", "-f", "markdown", "-t", "json"], input=markdown.encode())
    )
    title = ast["blocks"][1]["c"][1][0]
    inlines = title["c"][2]
    if url:
        assert inlines[0]["t"] == "Link"
        assert inlines[0]["c"][2][0] == url
        inlines = inlines[0]["c"][1]
    assert [item["t"] for item in inlines].count("Emph") == 1
    assert inlines[-1]["c"] == [
        {"t": "Str", "c": "Model"},
        {"t": "Space"},
        {"t": "Str", "c": "alpha"},
    ]


@pytest.mark.parametrize("phrases", [["absent"], ["Model", "Model alpha"], ["Model", "Model"]])
def test_invalid_title_italics_fail_during_source_validation(phrases):
    with pytest.raises(ValidationError, match="title italics"):
        Publication.model_validate(publication(title_italics=phrases))
