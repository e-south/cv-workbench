"""
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/tests/build/test_markdown.py

Tests canonical markdown materialization.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from cvworkbench.build.markdown import build_markdown
from cvworkbench.inputs.sot import load_sot
from cvworkbench.variants import load_variant


def test_markdown_includes_role_divs_and_tags() -> None:
    sot = load_sot(Path("sot.sample"))
    variant = load_variant(Path("config/variants/base.yaml"))

    content = build_markdown(sot, variant)

    assert "::: {#role-" in content
    assert ".tag-infra" in content
    assert "## Experience" in content


def test_markdown_formats_year_dates() -> None:
    sot = load_sot(Path("sot.sample"))
    variant = load_variant(Path("config/variants/base.yaml"))

    content = build_markdown(sot, variant)

    assert "2014 — 2018" in content


def test_markdown_includes_namespaced_tags() -> None:
    sot = load_sot(Path("sot.sample"))
    variant = load_variant(Path("config/variants/base.yaml"))

    content = build_markdown(sot, variant)

    assert ".tag-domain" in content
    assert ".tag-domain-synthetic-biology" in content


def test_markdown_includes_author_role_classes() -> None:
    sot = load_sot(Path("sot.sample"))
    variant = load_variant(Path("config/variants/base.yaml"))

    content = build_markdown(sot, variant)

    assert "[Alex Example]{.author .role-self .role-co-first}" in content


def test_markdown_uses_summary_snippet_when_present() -> None:
    sot = load_sot(Path("sot.sample"))
    variant = load_variant(Path("config/variants/base.yaml"))

    content = build_markdown(sot, variant)

    assert "Snippet summary override for sample" in content
    assert "Platform-focused engineer with a track record" not in content


def test_markdown_includes_section_intro_snippet() -> None:
    sot = load_sot(Path("sot.sample"))
    variant = load_variant(Path("config/variants/base.yaml"))

    content = build_markdown(sot, variant)

    assert "Selected experience across research and industry." in content


def test_markdown_only_renders_configured_contact_fields(tmp_path: Path) -> None:
    variant_path = tmp_path / "public.yaml"
    variant_path.write_text(
        "\n".join(
            [
                "variant:",
                "  id: public",
                "  contact_fields: [email, location]",
                "  order: [summary]",
                "  outputs: [md]",
            ]
        )
        + "\n"
    )
    variant = load_variant(variant_path)
    sot = {
        "person": {
            "name": "Alex Example",
            "label": "Private label",
            "email": "alex@example.com",
            "phone": "+1 555 555 0100",
            "location": {"city": "Boston", "region": "MA"},
            "links": [{"label": "Profile", "url": "https://example.com"}],
        }
    }

    content = build_markdown(sot, variant)

    assert "alex@example.com" in content
    assert "Boston, MA" in content
    assert "+1 555 555 0100" not in content
    assert "Private label" not in content
    assert "https://example.com" not in content
