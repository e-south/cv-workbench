"""Passive reading views retain semantic text without widening disclosure."""

import pytest
import yaml

from cvworkbench.ops.publication.pdf import PublicPdfError
from cvworkbench.ops.publication.policy import load_publish_config
from cvworkbench.ops.publication.reading import build_reading_html
from cvworkbench.variants import load_variant
from tests.ops.publication.test_pdf import _write_workspace


def render(tmp_path, markdown, links=frozenset()):
    _, variant, policy, sot = _write_workspace(tmp_path)
    return build_reading_html(
        markdown.encode(),
        allowed_links=links,
        person=yaml.safe_load((sot / "person.yaml").read_text()),
        variant=load_variant(variant),
        publish=load_publish_config(policy),
    ).decode()


def test_reading_preserves_semantics_and_self_closing_breaks(tmp_path):
    result = render(
        tmp_path,
        '<h1>Example</h1><h2>Skills</h2><ul><li><em>Model alpha</em><br />Methods</li></ul><span class="entry-date" style="color:red">2026</span>',
    )
    assert "<h1>Example</h1>" in result
    assert "<h2>Skills</h2>" in result
    assert "<em>Model alpha</em><br>" in result
    assert 'class="entry-date"' in result
    assert "style=" not in result


@pytest.mark.parametrize(
    "markdown",
    [
        "<script>alert(1)</script>",
        '<img src="https://example.org/image">',
        '<a href="https://example.org/unknown">Unknown</a>',
        '<a href="javascript:alert">Bad</a>',
        "555.867.5309",
        "other@example.org",
        "<h2>References</h2><p>Private contact</p>",
    ],
)
def test_reading_rejects_unsafe_or_private_content(tmp_path, markdown):
    with pytest.raises(PublicPdfError):
        render(tmp_path, markdown, frozenset({"javascript:alert"}))


def test_reading_preserves_native_section_wrappers(tmp_path):
    result = render(
        tmp_path, '<section class="entry-group"><h3>Training</h3><p>Methods</p></section>'
    )
    assert '<section class="entry-group"><h3>Training</h3>' in result


@pytest.mark.parametrize(
    "css",
    [
        b'@import "https://example.org/a.css";',
        b"body{background:url(https://example.org)}",
        b"</style><script>alert(1)</script>",
        b"/* /Users/example/private */",
    ],
)
def test_reading_rejects_external_or_private_styles(tmp_path, css):
    _, variant, policy, sot = _write_workspace(tmp_path)
    with pytest.raises(PublicPdfError):
        build_reading_html(
            b"<h1>Example</h1>",
            stylesheet=css,
            allowed_links=frozenset(),
            person=yaml.safe_load((sot / "person.yaml").read_text()),
            variant=load_variant(variant),
            publish=load_publish_config(policy),
        )


def test_reading_preserves_declared_native_page_boundary(tmp_path):
    result = render(
        tmp_path,
        '<h1>Example</h1><p>First page</p><h2 style="break-before: page">Training</h2><p>Second page</p>',
    )
    assert '<h2 class="cv-page-break-before">Training</h2>' in result
